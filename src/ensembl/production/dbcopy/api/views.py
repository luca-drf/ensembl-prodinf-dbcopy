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
from ensembl.production.dbcopy.lookups import get_database_set, get_table_set
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView


class ListDatabases(APIView):
    """
    View to list all databases from a given server
    """

    def get(self, request, *args, **kwargs):
        """
        Return a list of all schema names
        """
        hostname = kwargs.get('host')
        port = kwargs.get('port')
        name_filter = request.query_params.get('search', '').replace('%', '.*').replace('_', '.')
        name_matches = request.query_params.getlist('matches[]')
        try:
            result = get_database_set(hostname, port, name_filter, name_matches)
        except ValueError as e:
            return Response(str(e), status=status.HTTP_404_NOT_FOUND)
        return Response(result)


class ListTables(APIView):
    """
    View to list all tables from a given database
    """

    def get(self, request, *args, **kwargs):
        """
        Return a list of tables
        """
        hostname = kwargs.get('host')
        port = kwargs.get('port')
        database = kwargs.get('database')
        name_filter = request.query_params.get('search', '')
        name_matches = request.query_params.getlist('matches[]')
        try:
            result = get_table_set(hostname, port, database, name_filter, name_matches)
        except ValueError as e:
            return Response(str(e), status=status.HTTP_404_NOT_FOUND)
        return Response(result)