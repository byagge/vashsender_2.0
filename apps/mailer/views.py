# mailer/views.py

from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.utils import timezone
import json
from datetime import datetime

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser

from .models import ContactList, Contact, ImportTask
from .serializers import ContactListSerializer, ContactSerializer, ContactListListSerializer, ContactListDetailSerializer, MailerDomainSerializer
from .utils import parse_emails, classify_email
from apps.billing.models import Plan


class ContactListViewSet(viewsets.ModelViewSet):
    """
    CRUD для ContactList и вложенные операции с Contact через @action.
    """
    serializer_class    = ContactListSerializer
    permission_classes  = [IsAuthenticated]
    parser_classes      = [MultiPartParser] + viewsets.ModelViewSet.parser_classes

    def get_queryset(self):
        return ContactList.objects.filter(owner=self.request.user)

    def get_serializer_class(self):
        if self.action == 'list':
            return ContactListListSerializer
        return ContactListDetailSerializer

    def create(self, request, *args, **kwargs):
        """
        Переопределяем метод создания, чтобы при дублировании имени вернуть 400 с ошибкой,
        вместо падения 500.
        """
        # Подготовим сериализатор (owner запишем в perform_create)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            self.perform_create(serializer)
        except IntegrityError:
            return Response(
                {'name': ['Список с таким именем уже существует']},
                status=status.HTTP_400_BAD_REQUEST
            )

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


    @action(detail=True, methods=['get', 'post'], url_path='contacts')
    def contacts(self, request, pk=None):
        """
        GET  /contactlists/{pk}/contacts/?page=1&page_size=20  — список контактов с пагинацией
        POST /contactlists/{pk}/contacts/  — добавить контакт { email, status }
        """
        contact_list = self.get_object()

        if request.method == 'GET':
            qs = contact_list.contacts.all().order_by('-id')
            # --- FILTERING ---
            search_query = request.query_params.get('search', '').strip()
            if search_query:
                qs = qs.filter(email__icontains=search_query)
            # --- PAGINATION ---
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 20))
            total = qs.count()
            num_pages = (total + page_size - 1) // page_size
            start = (page - 1) * page_size
            end = start + page_size
            page_qs = qs[start:end]
            ser = ContactSerializer(page_qs, many=True)
            return Response({
                'results': ser.data,
                'count': total,
                'page': page,
                'num_pages': num_pages,
            })

        # --- ОГРАНИЧЕНИЕ ПО ТАРИФУ ---
        user = request.user
        plan = getattr(user, 'current_plan', None)
        if not plan:
            return Response({'error': 'Не найден тариф пользователя.'}, status=status.HTTP_400_BAD_REQUEST)
        contact_limit = getattr(plan, 'subscribers', 0)
        # Считаем общее число контактов во всех списках пользователя
        total_contacts = Contact.objects.filter(contact_list__owner=user).count()
        
        if contact_limit and total_contacts >= contact_limit:
            error_message = f'Превышен лимит контактов.'
            return Response({'error': error_message}, status=status.HTTP_400_BAD_REQUEST)
        # --- КОНЕЦ ОГРАНИЧЕНИЯ ---

        ser = ContactSerializer(data=request.data)
        
        if ser.is_valid():
            try:
                # Проверяем, не существует ли уже такой email в этом списке
                email = ser.validated_data['email']
                if Contact.objects.filter(contact_list=contact_list, email=email).exists():
                    return Response({'email': ['Этот email уже существует в данном списке']}, status=status.HTTP_400_BAD_REQUEST)
                
                contact = ser.save(contact_list=contact_list)
                return Response(ser.data, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({'error': f'Ошибка при сохранении контакта: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)


    @action(detail=True, methods=['delete'], url_path='contacts/(?P<cid>[^/.]+)')
    def delete_contact(self, request, pk=None, cid=None):
        """
        DELETE /contactlists/{pk}/contacts/{cid}/
        """
        contact_list = self.get_object()
        contact = get_object_or_404(Contact, pk=cid, contact_list=contact_list)
        contact.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


    @action(detail=True, methods=['post'], url_path='import')
    def import_contacts(self, request, pk=None):
        """
        POST /contactlists/{pk}/import/ — асинхронный импорт контактов с полной валидацией
        """
        import os
        import tempfile
        
        contact_list = self.get_object()
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'detail': 'No file uploaded.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Создаем задачу импорта
        import_task = ImportTask.objects.create(
            contact_list=contact_list,
            filename=file_obj.name,
            status=ImportTask.PENDING
        )

        try:
            # Сохраняем файл во временную директорию
            temp_dir = os.path.join(tempfile.gettempdir(), 'vashsender_imports')
            os.makedirs(temp_dir, exist_ok=True)
            
            file_path = os.path.join(temp_dir, f"{import_task.id}_{file_obj.name}")
            
            with open(file_path, 'wb+') as destination:
                for chunk in file_obj.chunks():
                    destination.write(chunk)
            
            # Запускаем асинхронную задачу
            from .tasks import import_contacts_async
            from django.conf import settings
            
            # Запускаем задачу асинхронно
            try:
                celery_task = import_contacts_async.delay(str(import_task.id), file_path)
                
                # Сохраняем ID Celery задачи для отслеживания
                import_task.celery_task_id = celery_task.id
                import_task.save()
                
                return Response({
                    'task_id': str(import_task.id),
                    'celery_task_id': celery_task.id,
                    'status': 'started',
                    'message': 'Импорт начат в фоновом режиме. Отслеживайте прогресс через API.'
                }, status=status.HTTP_202_ACCEPTED)
            except Exception as e:
                # Если не удалось запустить задачу Celery, выполняем синхронно
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to start Celery task: {e}, executing synchronously", exc_info=True)
                
                # Выполняем задачу синхронно через apply
                try:
                    result = import_contacts_async.apply(args=[str(import_task.id), file_path])
                    if result.successful():
                        import_task.status = ImportTask.COMPLETED
                    else:
                        import_task.status = ImportTask.FAILED
                        import_task.error_message = str(result.result) if result.result else str(e)
                    import_task.save()
                except Exception as sync_error:
                    logger.error(f"Failed to execute task synchronously: {sync_error}", exc_info=True)
                    import_task.status = ImportTask.FAILED
                    import_task.error_message = f"Celery error: {e}, Sync error: {sync_error}"
                    import_task.save()
                
                return Response({
                    'task_id': str(import_task.id),
                    'status': import_task.status,
                    'error': import_task.error_message,
                    'message': 'Импорт выполнен синхронно (Celery недоступен).'
                }, status=status.HTTP_200_OK)
            
        except Exception as e:
            # Обновляем задачу с ошибкой
            import_task.status = ImportTask.FAILED
            import_task.error_message = str(e)
            import_task.completed_at = timezone.now()
            import_task.save()
            
            return Response({
                'detail': f'Import failed: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'], url_path='import-status')
    def import_status(self, request, pk=None):
        """
        GET /contactlists/{pk}/import-status/ — получить статус задач импорта
        """
        contact_list = self.get_object()
        tasks = ImportTask.objects.filter(contact_list=contact_list).order_by('-created_at')[:10]
        
        tasks_data = []
        for task in tasks:
            # Если есть Celery task ID, получаем дополнительную информацию
            celery_info = {}
            if task.celery_task_id:
                try:
                    from celery.result import AsyncResult
                    celery_result = AsyncResult(task.celery_task_id)
                    celery_info = {
                        'celery_status': celery_result.status,
                        'celery_info': celery_result.info if celery_result.info else {},
                        'celery_successful': celery_result.successful(),
                        'celery_failed': celery_result.failed(),
                    }
                except Exception:
                    celery_info = {'celery_error': 'Не удалось получить статус Celery задачи'}
            
            task_data = {
                'id': str(task.id),
                'filename': task.filename,
                'status': task.status,
                'celery_task_id': task.celery_task_id,
                'total_emails': task.total_emails,
                'processed_emails': task.processed_emails,
                'progress_percentage': task.progress_percentage,
                'imported_count': task.imported_count,
                'invalid_count': task.invalid_count,
                'blacklisted_count': task.blacklisted_count,
                'error_count': task.error_count,
                'error_message': task.error_message,
                'started_at': task.started_at.isoformat() if task.started_at else None,
                'completed_at': task.completed_at.isoformat() if task.completed_at else None,
                'duration': task.duration,
                'created_at': task.created_at.isoformat(),
                **celery_info
            }
            tasks_data.append(task_data)
        
        return Response({
            'tasks': tasks_data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='import-tasks')
    def import_tasks(self, request):
        """
        GET /contactlists/import-tasks/ — получить все задачи импорта пользователя
        """
        tasks = ImportTask.objects.filter(contact_list__owner=request.user).order_by('-created_at')[:50]
        
        tasks_data = []
        for task in tasks:
            tasks_data.append({
                'id': str(task.id),
                'filename': task.filename,
                'contact_list_name': task.contact_list.name,
                'status': task.status,
                'total_emails': task.total_emails,
                'processed_emails': task.processed_emails,
                'progress_percentage': task.progress_percentage,
                'imported_count': task.imported_count,
                'invalid_count': task.invalid_count,
                'blacklisted_count': task.blacklisted_count,
                'error_count': task.error_count,
                'error_message': task.error_message,
                'started_at': task.started_at.isoformat() if task.started_at else None,
                'completed_at': task.completed_at.isoformat() if task.completed_at else None,
                'duration': task.duration,
                'created_at': task.created_at.isoformat()
            })
        
        return Response({
            'tasks': tasks_data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['delete'], url_path='import-tasks/(?P<task_id>[^/.]+)/delete')
    def delete_import_task(self, request, task_id=None):
        """
        DELETE /contactlists/import-tasks/{task_id}/delete/ — удалить задачу импорта
        """
        try:
            task = ImportTask.objects.get(
                id=task_id,
                contact_list__owner=request.user
            )
            task.delete()
            return Response({'detail': 'Task deleted successfully'}, status=status.HTTP_204_NO_CONTENT)
        except ImportTask.DoesNotExist:
            return Response({'detail': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'], url_path='import-fast')
    def import_contacts_fast(self, request, pk=None):
        """
        POST /contactlists/{pk}/import-fast/ — быстрый импорт контактов без валидации
        """
        import time
        start_time = time.time()
        
        contact_list = self.get_object()
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'detail': 'No file uploaded.'},
                            status=status.HTTP_400_BAD_REQUEST)

        emails = parse_emails(file_obj, file_obj.name)
        total_emails = len(emails)
        
        # Быстрый импорт без валидации
        contacts_to_create = []
        processed = 0
        
        for email in emails:
            try:
                processed += 1
                
                # Проверяем только базовый синтаксис
                if '@' in email and '.' in email.split('@')[1]:
                    new_contact = Contact(
                        contact_list=contact_list,
                        email=email.lower().strip(),
                        status=Contact.VALID  # Предполагаем что все валидные
                    )
                    contacts_to_create.append(new_contact)
                
                # Батчинг: сохраняем каждые 1000 контактов
                if len(contacts_to_create) >= 1000:
                    try:
                        Contact.objects.bulk_create(contacts_to_create, ignore_conflicts=True)
                        contacts_to_create = []
                    except Exception:
                        contacts_to_create = []
                        
            except Exception:
                continue
        
        # Сохраняем оставшиеся контакты
        if contacts_to_create:
            try:
                Contact.objects.bulk_create(contacts_to_create, ignore_conflicts=True)
            except Exception:
                pass

        elapsed_time = time.time() - start_time

        return Response({
            'imported': processed,
            'total_processed': processed,
            'total_in_file': total_emails,
            'elapsed_time': round(elapsed_time, 2),
            'message': 'Fast import completed. Run validation separately if needed.'
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='export')
    def export_contacts(self, request, pk=None):
        """
        POST /contactlists/{pk}/export/ — экспорт контактов в файл
        """
        contact_list = self.get_object()
        format_type = request.data.get('format', 'txt')
        types = request.data.get('types', [])

        # Создаем ZIP архив для всех файлов
        import zipfile
        from io import BytesIO
        from django.core.files.base import ContentFile

        # Создаем буфер для ZIP файла
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Экспортируем каждый тип контактов в отдельный файл
            for contact_type in types:
                # Получаем контакты текущего типа
                contacts = Contact.objects.filter(
                    contact_list=contact_list,
                    status=contact_type
                ).values_list('email', flat=True).order_by('email')

                if contacts:
                    # Формируем содержимое файла в зависимости от формата
                    if format_type == 'txt':
                        content = '\n'.join(contacts)
                        content_type = 'text/plain'
                    elif format_type == 'csv':
                        content = 'email\n' + '\n'.join(contacts)
                        content_type = 'text/csv'
                    elif format_type == 'json':
                        content = json.dumps(list(contacts), indent=2)
                        content_type = 'application/json'
                    else:
                        return Response(
                            {'error': 'Unsupported format'}, 
                            status=status.HTTP_400_BAD_REQUEST
                        )

                    # Создаем имя файла для текущего типа
                    type_names = {
                        'valid': 'действительные',
                        'invalid': 'недействительные',
                        'blacklist': 'черный_список'
                    }
                    filename = f'contacts_{contact_list.name}_{type_names[contact_type]}_{datetime.now().strftime("%Y-%m-%d")}.{format_type}'
                    
                    # Добавляем файл в ZIP архив
                    zip_file.writestr(filename, content)

        # Если нет контактов ни одного типа
        if zip_file.namelist() == []:
            return Response(
                {'error': 'No contacts found for selected types'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Подготавливаем ZIP файл для отправки
        zip_buffer.seek(0)
        response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="contacts_{contact_list.name}_{datetime.now().strftime("%Y-%m-%d")}.zip"'
        return response

    @action(detail=True, methods=['post'], url_path='import-optimized')
    def import_contacts_optimized(self, request, pk=None):
        """
        POST /contactlists/{pk}/import-optimized/ — оптимизированный импорт для больших объемов
        """
        import time
        from django.db import transaction
        start_time = time.time()
        
        contact_list = self.get_object()
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'detail': 'No file uploaded.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Создаем задачу импорта
        import_task = ImportTask.objects.create(
            contact_list=contact_list,
            filename=file_obj.name,
            status=ImportTask.PROCESSING
        )

        try:
            # Читаем email адреса из файла
            emails = parse_emails(file_obj, file_obj.name)
            total_emails = len(emails)
            
            # Обновляем задачу с общим количеством
            import_task.total_emails = total_emails
            import_task.save()
            
            added = 0
            invalid_count = 0
            blacklisted_count = 0
            error_count = 0
            processed = 0
            
            # Получаем все существующие email для быстрой проверки
            existing_emails = set(Contact.objects.filter(
                contact_list=contact_list
            ).values_list('email', flat=True))
            
            # Обрабатываем email большими батчами
            batch_size = 1000  # Большой размер батча
            contacts_to_create = []
            
            for i, email in enumerate(emails):
                try:
                    processed += 1
                    
                    # Обновляем прогресс каждые 1000 email
                    if processed % 1000 == 0:
                        import_task.processed_emails = processed
                        import_task.save()
                    
                    # Быстрая проверка существования
                    if email in existing_emails:
                        continue
                    
                    # Быстрая валидация без DNS для большинства доменов
                    from .utils import validate_email_fast
                    validation_result = validate_email_fast(email)
                    
                    if validation_result['is_valid']:
                        status_code = validation_result['status']
                        
                        new_contact = Contact(
                            contact_list=contact_list,
                            email=email,
                            status=status_code
                        )
                        contacts_to_create.append(new_contact)
                        added += 1
                        if status_code == Contact.BLACKLIST:
                            blacklisted_count += 1
                    else:
                        new_contact = Contact(
                            contact_list=contact_list,
                            email=email,
                            status=Contact.INVALID
                        )
                        contacts_to_create.append(new_contact)
                        invalid_count += 1
                    
                    # Сохраняем большими батчами
                    if len(contacts_to_create) >= batch_size:
                        with transaction.atomic():
                            Contact.objects.bulk_create(contacts_to_create, ignore_conflicts=True)
                        contacts_to_create = []
                        
                except Exception:
                    error_count += 1
                    continue
            
            # Сохраняем оставшиеся контакты
            if contacts_to_create:
                with transaction.atomic():
                    Contact.objects.bulk_create(contacts_to_create, ignore_conflicts=True)

            # Завершаем задачу
            elapsed_time = time.time() - start_time
            import_task.status = ImportTask.COMPLETED
            import_task.processed_emails = processed
            import_task.imported_count = added
            import_task.invalid_count = invalid_count
            import_task.blacklisted_count = blacklisted_count
            import_task.error_count = error_count
            import_task.completed_at = timezone.now()
            import_task.save()

            return Response({
                'task_id': str(import_task.id),
                'imported': added,
                'invalid_count': invalid_count,
                'blacklisted_count': blacklisted_count,
                'error_count': error_count,
                'total_processed': processed,
                'total_in_file': total_emails,
                'elapsed_time': round(elapsed_time, 2),
                'status': 'completed'
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            # Обновляем задачу с ошибкой
            import_task.status = ImportTask.FAILED
            import_task.error_message = str(e)
            import_task.completed_at = timezone.now()
            import_task.save()
            
            return Response({
                'detail': f'Import failed: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ListSpaView(LoginRequiredMixin, TemplateView):
    template_name = 'list.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_admin'] = self.request.user.is_staff
        return context


class ImportTasksView(LoginRequiredMixin, TemplateView):
    template_name = 'import_tasks.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_admin'] = self.request.user.is_staff
        return context


class DomainProxyViewSet(viewsets.ModelViewSet):
    """
    Проксирует управление доменами для раздела mailer, используя apps.emails.Domain.
    На create сразу генерирует DKIM и возвращает реальные DNS записи.
    """
    serializer_class = MailerDomainSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        from apps.emails.models import Domain
        return Domain.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=True, methods=['post'], url_path='generate-dkim')
    def generate_dkim(self, request, pk=None):
        from apps.emails.models import Domain
        domain = Domain.objects.get(id=pk, owner=request.user)
        ok = domain.generate_dkim_keys()
        if ok:
            return Response({'message': 'DKIM сгенерирован', 'dkim_dns_record': domain.dkim_dns_record})
        return Response({'error': 'Не удалось сгенерировать DKIM'}, status=status.HTTP_400_BAD_REQUEST)

