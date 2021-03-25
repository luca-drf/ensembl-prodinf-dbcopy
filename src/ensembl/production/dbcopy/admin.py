#   See the NOTICE file distributed with this work for additional information
#   regarding copyright ownership.
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#       http://www.apache.org/licenses/LICENSE-2.0
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter
from django.contrib.admin.utils import model_ngettext
from django.db.models import Count, F, Q
from django.utils.html import format_html
from django_admin_inline_paginator.admin import TabularInlinePaginated
from ensembl.production.dbcopy.forms import RequestJobForm, GroupInlineForm
from ensembl.production.dbcopy.models import Host, RequestJob, Group, TargetHostGroup, TransferLog
from ensembl.production.djcore.admin import SuperUserAdmin
from ensembl.production.djcore.filters import UserFilter


class GroupInline(admin.TabularInline):
    model = Group
    extra = 1
    form = GroupInlineForm
    fields = ('group_name',)
    verbose_name = "Group restriction"
    verbose_name_plural = "Group restrictions"


@admin.register(TargetHostGroup)
class TargetHostGroupAdmin(admin.ModelAdmin, SuperUserAdmin):
    list_display = ('target_group_name', 'get_hosts')
    fields = ('target_group_name', 'target_host')
    search_fields = ('target_group_name', 'target_host__name')

    def get_hosts(self, obj):
        return ", ".join([str(g) for g in obj.target_host.all()])


class TargetGroupInline(admin.TabularInline):
    model = TargetHostGroup.target_host.through


@admin.register(Host)
class HostItemAdmin(admin.ModelAdmin, SuperUserAdmin):
    class Media:
        css = {
            'all': ('css/db_copy.css',)
        }

    # form = HostRecordForm
    inlines = (GroupInline, TargetGroupInline)
    list_display = ('name', 'port', 'mysql_user', 'virtual_machine', 'mysqld_file_owner', 'get_target_groups', 'active')
    fields = ('name', 'port', 'mysql_user', 'virtual_machine', 'mysqld_file_owner', 'active')
    search_fields = ('name', 'port', 'mysql_user', 'virtual_machine', 'mysqld_file_owner', 'active')

    def get_target_groups(self, obj):
        return ", ".join([str(each_group.target_group_name)
                          for each_group in TargetHostGroup.objects.filter(target_host__auto_id=obj.auto_id)
                          ])

    get_target_groups.short_description = 'Host Target Groups '


class OverallStatusFilter(SimpleListFilter):
    title = 'status'  # or use _('country') for translated title
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        status = set([s.overall_status for s in model_admin.model.objects.all()])
        return [(s, s) for s in status]

    def queryset(self, request, queryset):
        if self.value() == 'Failed':
            qs = queryset.filter(end_date__isnull=False, status__isnull=False)
            return qs.filter(transfer_logs__end_date__isnull=True).annotate(
                count_transfer=Count('transfer_logs')).filter(count_transfer__gt=0)
        elif self.value() == 'Complete':
            qs = queryset.filter(end_date__isnull=False, status__isnull=False)
            return qs.exclude(transfer_logs__end_date__isnull=True)
        elif self.value() == 'Running':
            qs = queryset.filter(end_date__isnull=True, status__isnull=True)
            return qs.annotate(count_transfer=Count('transfer_logs')).filter(count_transfer__gt=0)
        elif self.value() == 'Submitted':
            qs = queryset.filter(end_date__isnull=True, status__isnull=True)
            return qs.annotate(count_transfer=Count('transfer_logs')).filter(count_transfer=0)




class TransferLogInline(TabularInlinePaginated):
    model = TransferLog
    per_page = 30
    fields = ('table_schema', 'table_name', 'renamed_table_schema', 'start_date', 'end_date', 'table_status')
    readonly_fields = ('table_schema', 'table_name', 'renamed_table_schema', 'start_date', 'end_date', 'table_status')
    can_delete = False
    ordering = F('end_date').asc(nulls_first=True), F('auto_id')

    def has_add_permission(self, request, obj):
        # TODO add superuser capability to add / copy an existing line / reset timeline to tweak copy job
        return False


@admin.register(RequestJob)
class RequestJobAdmin(admin.ModelAdmin):
    class Media:
        js = (
            # '//cdnjs.cloudflare.com/ajax/libs/jqueryui/1.12.1/jquery-ui.min.js',
            'js/dbcopy/multiselect.js',
        )
        css = {
            'all': ('css/db_copy.css',)
        }

    actions = ['resubmit_jobs', ]
    inlines = (TransferLogInline,)
    form = RequestJobForm
    list_display = ('job_id', 'src_host', 'src_incl_db', 'src_skip_db', 'tgt_host', 'tgt_db_name', 'user',
                    'start_date', 'end_date', 'request_date', 'overall_status')
    search_fields = ('job_id', 'src_host', 'src_incl_db', 'src_skip_db', 'tgt_host', 'tgt_db_name', 'user',
                     'start_date', 'end_date', 'request_date')
    list_filter = ('tgt_host', 'src_host', UserFilter, OverallStatusFilter)
    ordering = ('-request_date', '-start_date')

    def get_queryset(self, request):
        return super().get_queryset(request)

    def has_change_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        # Allow delete only for superusers and obj owners
        return request.user.is_superuser or (obj is not None and request.user.username == obj.user)

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        form.user = request.user
        return form

    def resubmit_jobs(self, request, queryset):
        for query in queryset:
            newJob = RequestJob.objects.get(pk=query.pk)
            newJob.pk = None
            newJob.request_date = None
            newJob.start_date = None
            newJob.end_date = None
            newJob.status = None
            newJob.save()
            message = 'Job {} resubmitted [new job_id {}]'.format(query.pk, newJob.pk)
            messages.add_message(request, messages.SUCCESS, message, extra_tags='', fail_silently=False)

    resubmit_jobs.short_description = 'Resubmit Jobs'

    def change_view(self, request, object_id, form_url='', extra_context=None):
        context = extra_context or {}
        search_query = request.GET.get('search_box')
        if search_query:
            transfers_logs = self.get_object(request, object_id).transfer_logs.filter(
                Q(table_name__contains=search_query) | Q(table_schema__contains=search_query) | Q(
                    tgt_host__contains=search_query) | Q(renamed_table_schema__contains=search_query))
        else:
            transfers_logs = self.get_object(request, object_id).transfer_logs
        # paginator = Paginator(transfers_logs.order_by(F('end_date').asc(nulls_first=True), F('auto_id')), 30)
        # page_number = request.GET.get('page', 1)
        # page = paginator.page(page_number)
        # context['transfer_logs'] = page
        context['label_create'] = 'Duplicate/Update' if 'from_request_job' in request.GET else 'Add'
        if transfers_logs.filter(end_date__isnull=True):
            context["running_copy"] = transfers_logs.filter(end_date__isnull=True).order_by(
                F('end_date').desc(nulls_first=True)).earliest('auto_id')
        return super().change_view(request, object_id, form_url, context)

    def _get_deletable_objects(self, queryset):
        return queryset.exclude(Q(status='Creating Requests') | Q(status='Processing Requests'))

    def get_deleted_objects(self, queryset, request):
        deletable_queryset = self._get_deletable_objects(queryset)
        return super().get_deleted_objects(deletable_queryset, request)

    def delete_queryset(self, request, queryset):
        deletable_queryset = self._get_deletable_objects(queryset)
        deleted_count, _rows_count = deletable_queryset.delete()
        message = "Successfully deleted %(count)d %(items)s." % {
            'count': deleted_count, 'items': model_ngettext(self.opts, deleted_count)
        }
        messages.add_message(request, messages.SUCCESS, message, extra_tags='', fail_silently=False)

    def message_user(self, *args, **kwargs):
        pass

    def log_deletion(self, request, obj, obj_display):
        if obj.status not in ('Creating Requests', 'Processing Requests'):
            super().log_deletion(request, obj, obj_display)

    def overall_status(self, obj):
        return format_html(
            '<div class="overall_status {}">{}</div>',
            obj.overall_status,
            obj.overall_status
        )

    def get_fields(self, request, obj=None):
        return super().get_fields(request, obj)

    def get_inlines(self, request, obj):
        """Hook for specifying custom inlines."""
        if obj:
            return super().get_inline(request, obj)
        else:
            return []
