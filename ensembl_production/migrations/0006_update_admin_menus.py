# Generated by Django 2.2.8 on 2020-01-23 16:02

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('ensembl_production', '0005_update_flask_apps')
    ]

    operations = [
        migrations.RunSQL(
            """
            UPDATE ensembl_production_services.sitetree_treeitem 
            SET url = REPLACE(url, '/app/admin/', '/admin/') 
            WHERE url LIKE '/app/admin/%'
            """),
        migrations.RunSQL(
            """
            DELETE FROM ensembl_production_services.flask_app 
            WHERE app_prod_url = 'admin'
            """)
    ]
