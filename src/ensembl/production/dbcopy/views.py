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
from django.shortcuts import redirect
from django.urls import reverse
from django.core.exceptions import ValidationError
import logging

from django.contrib.auth.decorators import login_required
from ensembl.production.core.db_introspects import get_database_set, get_table_set

from ensembl.production.dbcopy.filters import get_filter_match
from ensembl.production.dbcopy.lookups import get_excluded_schemas
from ensembl.production.dbcopy.models import RequestJob
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


@require_http_methods(["GET", "POST"])
def reset_failed_jobs(request, *args, **kwargs):
    job_id = kwargs['job_id']
    request_job = RequestJob.objects.filter(job_id=job_id)
    request_job.update(status='Manually Launched by Production team')
    obj = request_job[0]
    url = reverse('admin:%s_%s_change' % (obj._meta.app_label, obj._meta.model_name),
                  args=[obj.job_id])
    messages.success(request, "All the failed jobs for %s have been successfully reset" % job_id)
    return redirect(url)


@login_required
@require_http_methods(['POST'])
def requestjob_checks_warning(request):
    import json
    from django.http import HttpResponse
    ajax_vars = {'dberrors': {}, 'dbwarnings': {}, 'tablewarnings': {}, 'tableerrors': {}}
    src_host = request.POST.get('src_host', 'None')
    tgt_hosts = request.POST.getlist('tgt_host', [])
    logger.info("All Post data %s", request.POST)
    src = src_host.split(':')
    hostname = src[0]
    port = src[1]
    if src_host:
        posted = request.POST.dict()
        posted.pop('csrfmiddlewaretoken')
        request_job = RequestJob(**posted)
        try:
            request_job.full_clean()
        except ValidationError as e:
            ajax_vars['dberrors'].update(e)
            return HttpResponse(json.dumps(ajax_vars),
                                status=400,
                                content_type='application/json')
    # 1. Retrieve on src_host
    #   All dbnames which match src_incl_db and retire all matching src_skip_dbs
    src_name_filter, src_name_match = get_filter_match(request.POST.getlist('src_incl_db', []))
    src_excl_filter, src_excl_match = get_filter_match(request.POST.getlist('src_skip_db', []))

    try:
        src_db_set_filter = get_database_set(hostname=hostname, port=port,
                                             name_filter=src_name_filter,
                                             excluded_schemas=get_excluded_schemas()) if src_name_filter else set()

        src_db_set_match = get_database_set(hostname=hostname, port=port,
                                            name_matches=src_name_match,
                                            excluded_schemas=get_excluded_schemas()) if src_name_match else set()
        src_db_set = src_db_set_match.union(src_db_set_filter)
        logger.info("initial src_db_set %s", src_db_set)
        excl_db_set_filter = get_database_set(hostname=hostname, port=port,
                                              name_filter=src_excl_filter,
                                              excluded_schemas=get_excluded_schemas()) if src_excl_filter else set()
        excl_db_set_match = get_database_set(hostname=hostname, port=port,
                                             name_matches=src_excl_match,
                                             excluded_schemas=get_excluded_schemas()) if src_excl_match else set()
        excl_db_set = excl_db_set_filter.union(excl_db_set_match)
        src_db_set = src_db_set.difference(excl_db_set)
        logger.info("exc_db_set %s", excl_db_set)
        logger.info("result_db_set %s", src_db_set)
        if len(src_db_set) == 0:
            raise ValueError("No db matching incl. [%s %s] / excl. [%s %s] " % (src_name_filter, src_name_match,
                                                                                src_excl_filter, src_excl_match))
    except ValueError as e:
        ajax_vars.update({'dberrors': {hostname: [str(e)]}})
        return HttpResponse(json.dumps(ajax_vars),
                            status=400,
                            content_type='application/json')

    # 2. For each target:
    #   Retrieve all dbnames which match tgt_db_name
    #   Diff with src_dbames
    tgt_name_filter, target_name_match = get_filter_match(request.POST.getlist('tgt_db_name', []))
    logger.debug("src_db_set %s", src_db_set)
    tgt_db_set_match = src_db_set
    # TODO manage tgt_name_filter
    if target_name_match:
        tgt_db_set_match = set(target_name_match)
        logger.debug("Updated src_db_set with renamed targets %s", target_name_match)
    for tgt_host in tgt_hosts:
        host = tgt_host.split(':')[0]
        port = tgt_host.split(':')[1]
        try:
            logger.debug("tgt db set %s %s", host, src_db_set)
            tgt_db_set = get_database_set(hostname=host, port=port,
                                          name_matches=tgt_db_set_match,
                                          excluded_schemas=get_excluded_schemas())
            logger.debug("Found on target %s", tgt_db_set)
            if len(tgt_db_set) > 0:
                ajax_vars['dbwarnings'].update({host: list(sorted(tgt_db_set))})
                if len(src_db_set) == 1:
                    # found a target db on target and source == 1
                    # Now just warning for table override
                    # 3. For each dbnames on src_incl_db
                    #   fetch all tables from src_incl_tables filtered by src_skip_tables
                    # 4. For each intersect dbnames
                    databases = tgt_name_filter or src_db_set
                    src_incl_table_filter, src_incl_table_match = get_filter_match(
                        request.POST.getlist('src_incl_tables', ''))
                    logger.debug('tgt_name_filter %s src_db_set %s', tgt_name_filter, src_db_set)
                    for database in databases:
                        try:
                            logger.debug('srcdbSet 1: %s,%s,%s,%s,%s', host, port, database, src_incl_table_filter,
                                         src_incl_table_match)
                            tgt_table_name_filter = get_table_set(hostname=host, port=port,
                                                                  database=database, name_filter=src_incl_table_filter) \
                                if src_incl_table_filter else set()
                            tgt_table_name_match = get_table_set(hostname=host, port=port,
                                                                 database=database, name_matches=src_incl_table_match) \
                                if src_incl_table_match else set()
                            tgt_table_name_set = tgt_table_name_filter.union(tgt_table_name_match)
                            logger.debug("table_name_matches %s", tgt_table_name_set)
                            if len(tgt_table_name_set) > 0:
                                ajax_vars['tablewarnings'].update({database: sorted(tgt_table_name_set)})
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
