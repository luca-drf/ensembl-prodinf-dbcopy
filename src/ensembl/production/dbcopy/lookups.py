# See the NOTICE file distributed with this work for additional information
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
import logging
import re
from functools import lru_cache

import sqlalchemy as sa
from dal import autocomplete
from django.core.exceptions import ObjectDoesNotExist
from django.utils.html import format_html
from ensembl.production.dbcopy.models import Dbs2Exclude

from .models import Host, Group

logger = logging.getLogger(__name__)


class SrcHostLookup(autocomplete.Select2QuerySetView):
    model = Host

    def get_queryset(self):
        qs = Host.objects.all()
        if self.q:
            qs = qs.filter(name__icontains=self.q).order_by('name')[:50]
        return qs

    def get_result_label(self, result):
        if result.active:
            active = 'badge-success';
            desc = 'Active'
        else:
            active = ''
            desc = 'Inactive'
        return format_html('<span class="badge badge-pill %s">%s</span><span> %s</span>' % (active, desc, result.name))

    def get_selected_result_label(self, result):
        return '%s:%s' % (result.name, result.port)

    def get_result_value(self, result):
        return '%s:%s' % (result.name, result.port)


class TgtHostLookup(autocomplete.Select2QuerySetView):
    model = Host

    def get_queryset(self):
        host_queryset = Host.objects.all()
        group_queryset = Group.objects.all()
        host_queryset_final = host_queryset
        # Checking that user is allowed to copy to the matching server
        # If he is not allowed, the server will be removed from the autocomplete
        if self.q:
            host_queryset = host_queryset.filter(name__icontains=self.q, active=True)
            host_queryset_final = host_queryset
            for host in host_queryset:
                group = group_queryset.filter(host_id=host.auto_id)
                if group:
                    host_groups = group.values_list('group_name', flat=True)
                    user_groups = self.request.user.groups.values_list('name', flat=True)
                    common_groups = set(host_groups).intersection(set(user_groups))
                    if not common_groups:
                        host_queryset_final = host_queryset.exclude(name=host.name)
        return host_queryset_final

    def get_selected_result_label(self, result):
            return '%s:%s' % (result.name, result.port)

    def get_result_value(self, result):
        return '%s:%s' % (result.name, result.port)


class DbLookup(autocomplete.Select2ListView):
    def get_list(self):
        """
        Return a list of all schema names
        """
        search = self.q or ''
        result = []
        if self.q:
            try:
                host = self.forwarded.get('db_host').split(':')[0]
                port = self.forwarded.get('db_host').split(':')[1]
                name_filter = search.replace('%', '.*').replace('_', '.')
                result = get_database_set(host, port, name_filter)
            except (ValueError, ObjectDoesNotExist) as e:
                # TODO manage proper error
                logger.error("Db Lookup query error: ", e)
                pass
        return result


class TableLookup(autocomplete.Select2ListView):
    def get_list(self):
        result = []
        if len(self.forwarded.get('src_incl_db')) > 1:
            return ['Cannot filter on table name on multiple dbs!!']
        if self.q and len(self.q) >= 2:
            try:
                host = self.forwarded.get('db_host').split(':')[0]
                port = self.forwarded.get('db_host').split(':')[1]
                database = self.forwarded.get('src_incl_db')[0]
                result = get_table_set(host, port, database, self.q)
            except (ValueError, ObjectDoesNotExist):
                # TODO manage proper error
                logger.error("Db Table Lookup query error: ", e)
                pass
        return result


def make_excluded_schemas():
    schemas = set()

    def closure():
        if not schemas:
            schemas.update(Dbs2Exclude.objects.values_list('table_schema', flat=True))
        return schemas

    return closure


get_excluded_schemas = make_excluded_schemas()


@lru_cache(maxsize=None)
def get_engine(hostname, port, password=''):
    host = Host.objects.filter(name=hostname, port=port).first()
    if not host:
        raise RuntimeError('No host corresponding to %s:%s' % (hostname, port))
    uri = 'mysql://{}:{}@{}:{}'.format(host.mysql_user,
                                       password,
                                       host.name,
                                       host.port)
    return sa.create_engine(uri, pool_recycle=3600)


def get_database_set(hostname, port, name_filter='', name_matches=[]):
    try:
        db_engine = get_engine(hostname, port)
    except RuntimeError as e:
        raise ValueError('Invalid hostname: {} or port: {}'.format(hostname, port)) from e
    database_list = sa.inspect(db_engine).get_schema_names()
    excluded_schemas = get_excluded_schemas()
    if name_matches:
        database_set = set(database_list)
        names_set = set(name_matches)
        return database_set.difference(excluded_schemas).intersection(names_set)
    else:
        try:
            filter_db_re = re.compile(name_filter)
        except re.error as e:
            raise ValueError('Invalid name_filter: {}'.format(name_filter)) from e
        return set(filter(filter_db_re.search, database_list)).difference(excluded_schemas)


def get_table_set(hostname, port, database, name_filter='', name_matches=[]):
    try:
        filter_table_re = re.compile(name_filter)
    except re.error as e:
        raise ValueError('Invalid name_filter: {}'.format(name_filter)) from e
    try:
        db_engine = get_engine(hostname, port)
    except RuntimeError as e:
        raise ValueError('Invalid hostname: {} or port: {}'.format(hostname, port)) from e
    try:
        table_list = sa.inspect(db_engine).get_table_names(schema=database)
    except sa.exc.OperationalError as e:
        raise ValueError('Invalid database: {}'.format(database)) from e
    excluded_schemas = get_excluded_schemas()
    if name_matches:
        table_set = set(table_list)
        table_names_set = set(name_matches)
        return table_set.difference(excluded_schemas).intersection(table_names_set)
    return set(filter(filter_table_re.search, table_list)).difference(excluded_schemas)
