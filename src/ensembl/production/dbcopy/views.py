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
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect
from django.urls import reverse
from django.core.exceptions import ValidationError
import logging

# from django.contrib.auth.decorators import login_required
from ensembl.production.core.db_introspects import get_database_set, get_table_set

from ensembl.production.dbcopy.lookups import get_excluded_schemas
from ensembl.production.dbcopy.models import RequestJob
from ensembl.production.dbcopy.utils import get_filters
from django.views.decorators.http import require_http_methods


logger = logging.getLogger(__name__)


@require_http_methods(["GET", "POST"])
@staff_member_required
def reset_failed_jobs(request, *args, **kwargs):
    job_id = kwargs['job_id']
    request_job = RequestJob.objects.filter(job_id=job_id)
    request_job.update(status='Manually Launched by Production team')
    obj = request_job[0]
    url = reverse('admin:%s_%s_change' % (obj._meta.app_label, obj._meta.model_name),
                  args=[obj.job_id])
    messages.success(request, "All the failed jobs for %s have been successfully reset" % job_id)
    return redirect(url)


@staff_member_required
@require_http_methods(['POST'])
def requestjob_checks_warning(request):
    import json
    from django.http import HttpResponse
    ajax_vars = {'dberrors': {}, 'dbwarnings': {}, 'tablewarnings': {}, 'tableerrors': {}}
    src_host = request.POST.get('src_host', 'None')
    tgt_hosts = request.POST.getlist('tgt_host', [])
    logger.debug("All Post data %s", request.POST)
    if src_host and tgt_hosts:
        hostname, port = src_host.split(':')
        posted = request.POST.dict()
        posted.pop('csrfmiddlewaretoken')
        request_job = RequestJob(**posted)
        try:
            exclude = 'tgt_host' if not tgt_hosts else None
            request_job.full_clean(exclude=exclude, validate_unique=False)
        except ValidationError as e:
            ajax_vars['dberrors'].update(e)
            return HttpResponse(json.dumps(ajax_vars), status=400, content_type='application/json')
        # 1. Retrieve on src_host
        #   All dbnames which match src_incl_db and retire all matching src_skip_dbs
        src_incl_filters = get_filters(request.POST.getlist('src_incl_db', []))
        src_skip_filters = get_filters(request.POST.getlist('src_skip_db', []))
        excluded_schemas = get_excluded_schemas()
        src_skip_db_set = excluded_schemas.union(src_skip_filters)
        try:
            src_db_set = get_database_set(hostname=hostname, port=port,
                                          incl_filters=src_incl_filters,
                                          skip_filters=src_skip_db_set)
            logger.info("result_db_set %s", src_db_set)
            if (not src_db_set) and (src_incl_filters or src_skip_filters):
                # only raise error if no match, but only if any filter specified
                raise ValueError("No db matching incl. %s / excl. %s " % (src_incl_filters, src_skip_filters))
        except ValueError as e:
            ajax_vars.update({'dberrors': {hostname: [str(e)]}})
            return HttpResponse(json.dumps(ajax_vars), status=400, content_type='application/json')

        # 2. For each target:
        #   Retrieve all dbnames which match tgt_db_name
        #   Diff with src_dbames
        tgt_db_names = set(request.POST.getlist('tgt_db_name', [])) or src_db_set
        for tgt_host in tgt_hosts:
            host, port = tgt_host.split(':')
            try:
                logger.debug("tgt db names %s %s", host, tgt_db_names)
                tgt_db_set = get_database_set(hostname=host, port=port,
                                              incl_filters=tgt_db_names,
                                              skip_filters=excluded_schemas)
                logger.debug("Found on target %s", tgt_db_set)
                if len(tgt_db_set) > 0:
                    ajax_vars['dbwarnings'].update({host: list(sorted(tgt_db_set))})
                    if len(src_db_set) == 1:
                        # found a target db on target and source == 1
                        database = src_db_set.pop()
                        incl_table_filter = get_filters(request.POST.getlist('src_incl_tables', []))
                        logger.debug('incl_table_filter %s src_db_set %s', incl_table_filter, src_db_set)
                        try:
                            logger.debug('srcdbSet 1: %s:%s/%s, %s', host, port, database, incl_table_filter)
                            tgt_table_names = get_table_set(hostname=host, port=port,
                                                            database=database,
                                                            incl_filters=incl_table_filter)
                            logger.debug("tgt_table_names %s", tgt_table_names)
                            if len(tgt_table_names) > 0:
                                ajax_vars['tablewarnings'].update({database: sorted(tgt_table_names)})
                        except ValueError as e:
                            # Error most likely raised when target db doesn't exists, this is no error!
                            # TODO check the above statement twice!
                            # ajax_vars['tableerrors'].update({host: [str(e)]})
                            pass
            except ValueError as e:
                logger.error("Inspect error %s", str(e))
                ajax_vars['dberrors'].update({host: [str(e)]})

    if len(ajax_vars['dberrors']) > 0 or len(ajax_vars['tableerrors']) > 0:
        status_code = 400
    elif len(ajax_vars['dbwarnings']) > 0 or len(ajax_vars['tablewarnings']) > 0:
        status_code = 409
    else:
        status_code = 200
    return HttpResponse(json.dumps(ajax_vars),
                        status=status_code,
                        content_type='application/json')


@staff_member_required
def group_choice(request, *args, **kwargs):
    from ensembl.production.dbcopy.models import Host, HostGroup

    host_id = request.POST.get("host_id")
    host_id = Host.objects.get(auto_id=host_id)
    for each_group in request.POST.getlist('group_name'):
        grp = HostGroup.objects.filter(group_name=[str(each_group)], host_id=request.POST.get("host_id"))
        if len(grp) > 0:
            continue
        new_group = HostGroup()
        new_group.group_name = each_group
        new_group.host_id = host_id  # Host.objects.get(auto_id=host_id)
        new_group.save()

    url = reverse('admin:ensembl_dbcopy_group_changelist')
    return redirect(url)
