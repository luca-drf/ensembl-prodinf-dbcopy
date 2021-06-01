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

import json

from django.contrib.auth import get_user_model
from django.db import connections, connection
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ensembl.production.dbcopy.models import RequestJob

User = get_user_model()


class RequestJobTest(APITestCase):
    """ Test module for RequestJob model """
    fixtures = ['ensembl_dbcopy']

    # Test requestjob endpoint
    def testRequestJob(self):
        # Check get all
        response = self.client.get(reverse('dbcopy_api:requestjob-list'))
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Test post
        response = self.client.post(reverse('dbcopy_api:requestjob-list'),
                                    {'src_host': 'mysql-ens-sta-1', 'src_incl_db': 'homo_sapiens_core_99_38',
                                     'tgt_host': 'mysql-ens-general-dev-1', 'user': 'testuser'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Test user email
        response_dict = json.loads(response.content.decode('utf-8'))
        self.assertEqual(response_dict['email_list'], 'testuser@ebi.ac.uk')
        # Test bad post
        response = self.client.post(reverse('dbcopy_api:requestjob-list'),
                                    {'src_host': '', 'src_incl_db': 'homo_sapiens_core_99_38',
                                     'tgt_host': 'mysql-ens-general-dev-1'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Test get
        response = self.client.get(
            reverse('dbcopy_api:requestjob-detail', kwargs={'job_id': '8f084180-07ae-11ea-ace0-9801a79243a5'}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Test bad get
        response = self.client.get(
            reverse('dbcopy_api:requestjob-detail', kwargs={'job_id': 'd662656c-0a18-11ea-ab6c-9801a79243a5'}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        # Test Transfer log
        response = self.client.get(
            reverse('dbcopy_api:requestjob-detail', kwargs={'job_id': 'ddbdc15a-07af-11ea-bdcd-9801a79243a5'}))
        response_dict = json.loads(response.content.decode('utf-8'))
        self.assertEqual(len(response_dict['transfer_log']), 2)
        # Test put
        response = self.client.put(
            reverse('dbcopy_api:requestjob-detail', kwargs={'job_id': '8f084180-07ae-11ea-ace0-9801a79243a5'}),
            {'src_host': 'mysql-ens-sta-1', 'src_incl_db': 'homo_sapiens_core_99_38',
             'tgt_host': 'mysql-ens-general-dev-2', 'user': 'testuser'})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        # Test patch
        response = self.client.patch(
            reverse('dbcopy_api:requestjob-detail', kwargs={'job_id': '8f084180-07ae-11ea-ace0-9801a79243a5'}),
            {'src_incl_db': 'homo_sapiens_funcgen_99_38'})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        # Test delete
        response = self.client.delete(
            reverse('dbcopy_api:requestjob-detail', kwargs={'job_id': '8f084180-07ae-11ea-ace0-9801a79243a5'}))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        job = RequestJob.objects.filter(job_id='8f084180-07ae-11ea-ace0-9801a79243a5').count()
        # jab has actually be deleted from DB
        self.assertEqual(0, job)
        # Test delete non existant
        response = self.client.delete(
            reverse('dbcopy_api:requestjob-detail', kwargs={'job_id': '673f3b10-09e6-11ea-9206-9801a79243a5'}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        req = RequestJob.objects.get(job_id='ddbdc15a-07af-11ea-bdcd-9801a79243a5')
        req.status = 'Processing Requests'
        req.save()
        response = self.client.delete(
            reverse('dbcopy_api:requestjob-detail', kwargs={'job_id': 'ddbdc15a-07af-11ea-bdcd-9801a79243a5'}))
        self.assertEqual(response.status_code, status.HTTP_406_NOT_ACCEPTABLE)

    # Test Source host endpoint
    def testSourceHost(self):
        # Test get
        response = self.client.get(reverse('dbcopy_api:srchost-detail', kwargs={'name': 'mysql-ens-sta-1'}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Test bad get
        response = self.client.get(reverse('dbcopy_api:srchost-detail', kwargs={'name': 'mysql-ens-compara-2'}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        # Test getting 2 mysql-ens-sta-2 servers
        response = self.client.get(reverse('dbcopy_api:srchost-list'), {'name': 'mysql-ens-sta'})
        response_dict = json.loads(response.content.decode('utf-8'))
        self.assertEqual(len(response_dict), 2)
        # Test getting mysql-ens-general-dev-1 server
        response = self.client.get(reverse('dbcopy_api:srchost-list'), {'name': 'mysql-ens-general'})
        response_dict = json.loads(response.content.decode('utf-8'))
        self.assertEqual(len(response_dict), 2)

    # Test Target host endpoint
    def testTargetHost(self):
        # Test get
        response = self.client.get(reverse('dbcopy_api:tgthost-detail', kwargs={'name': 'mysql-ens-sta-1'}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Test bad get
        response = self.client.get(reverse('dbcopy_api:tgthost-detail', kwargs={'name': 'mysql-ens-compara-2'}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        # Test getting 2 mysql-ens-sta servers with allowed user
        User.objects.get(username='testuser')
        self.client.login(username='testuser', password='testgroup123')
        response = self.client.get(reverse('dbcopy_api:tgthost-list'), {'name': 'mysql-ens-sta'})
        response_dict = json.loads(response.content.decode('utf-8'))
        self.assertEqual(len(response_dict), 2)
        # Test getting 2 mysql-ens-sta servers with non-allowed user
        User.objects.get(username='testuser2')
        self.client.login(username='testuser2', password='testgroup1234')
        response = self.client.get(reverse('dbcopy_api:tgthost-list'), {'name': 'mysql-ens-sta'})
        response_dict = json.loads(response.content.decode('utf-8'))
        self.assertEqual(len(response_dict), 1)
        # Test getting mysql-ens-general-dev-1 server
        response = self.client.get(reverse('dbcopy_api:tgthost-list'), {'name': 'mysql-ens-general'})
        response_dict = json.loads(response.content.decode('utf-8'))
        self.assertEqual(len(response_dict), 2)

    def testRequestModelClean(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            # test db_name repeated on same target
            job = RequestJob.objects.create(src_host="host1",
                                            tgt_host="host4,host1",
                                            src_incl_db="db1,db4",
                                            tgt_db_name="db5,db1")
        with self.assertRaises(ValidationError):
            # test target db name not set at all 9same target dn names
            job = RequestJob.objects.create(src_host="host1",
                                            tgt_host="host1,host3",
                                            src_incl_db="db1")
        with self.assertRaises(ValidationError):
            # test target host contains src host and all db selected
            job = RequestJob.objects.create(src_host="host1",
                                            tgt_host="host2,host1")
        # Test a normal job would pass.
        job = RequestJob.objects.create(src_host="host2",
                                        tgt_host="host4,host3",
                                        src_incl_db="db1,db4",
                                        tgt_db_name="db5,db1")
        self.assertIsNotNone(job)

        # test a job with same target but different db name would pass
        job = RequestJob.objects.create(src_host="host2",
                                        tgt_host="host2",
                                        src_incl_db="db1",
                                        tgt_db_name="db5")
        self.assertIsNotNone(job)


class DBIntrospectTest(APITestCase):

    @classmethod
    def setUpTestData(cls):
        with connection.cursor() as cursor:
            cursor.execute("DROP DATABASE IF EXISTS `test_homo_sapiens`")
            cursor.execute("CREATE DATABASE `test_homo_sapiens`")
            cursor.execute("CREATE TABLE test_homo_sapiens.`assembly` (`id` INT(10))")
            cursor.execute("CREATE TABLE test_homo_sapiens.`assembly_exception` (`id` INT(10))")
            cursor.execute("CREATE TABLE test_homo_sapiens.`coord_system` (`id` INT(10))")
        cls.host = connections.databases['default'].get('HOST', 'localhost')
        cls.port = connections.databases['default'].get('PORT', 3306)
        cls.database = 'test_homo_sapiens'

    @classmethod
    def tearDownClass(cls):
        with connection.cursor() as cursor:
            cursor.execute("DROP DATABASE IF EXISTS `test_homo_sapiens`")

    def testDatabaseList(self):
        # Test getting test Production dbs
        args = {'host': self.host, 'port': self.port}
        print(reverse('dbcopy_api:databaselist', kwargs=args))
        response = self.client.get(reverse('dbcopy_api:databaselist', kwargs=args),
                                   {'search': 'test_homo'})
        print("content", response.content)
        response_list = json.loads(response.content.decode('utf-8'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response_list), 1)
        self.assertEqual(response_list[0], 'test_homo_sapiens')
        response = self.client.get(reverse('dbcopy_api:databaselist',
                                           kwargs={**args, 'host': 'bad-host'}),
                                   {'search': 'test_production_services'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(reverse('dbcopy_api:databaselist', kwargs=args),
                                   {'search': 'no_result_search'})
        response_list = json.loads(response.content.decode('utf-8'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_list), 0)
        response = self.client.get(reverse('dbcopy_api:databaselist', kwargs=args),
                                   {'matches[]': ['test_homo_sapiens']})
        response_list = json.loads(response.content.decode('utf-8'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_list), 1)
        response = self.client.get(reverse('dbcopy_api:databaselist', kwargs=args),
                                   {'matches[]': ['no_match']})
        response_list = json.loads(response.content.decode('utf-8'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_list), 0)

    def testTableList(self):
        args = {'host': self.host,
                'port': self.port,
                'database': self.database}
        # Test getting meta_key table for Production dbs
        response = self.client.get(reverse('dbcopy_api:tablelist', kwargs=args),
                                   {'search': 'ass'})
        response_list = json.loads(response.content.decode('utf-8'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_list), 2)
        args['host'] = 'badhost-name'
        response = self.client.get(reverse('dbcopy_api:tablelist', kwargs=args),
                                   {'search': 'meta'})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        args['host'] = self.host
        response = self.client.get(reverse('dbcopy_api:tablelist', kwargs=args),
                                   {'search': 'unknown'})
        response_list = json.loads(response.content.decode('utf-8'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_list), 0)
