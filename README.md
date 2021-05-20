Ensembl Django DBCopy portable App
==================================

Ensembl DBCopy service support Database manager

Quick start
-----------

1. Create a project

Check out repo from github


2. Create an app within your project

    2.1 Init your app
    
    ```run ./manage.py migrate ensembl_dbcopy```

    2.2 Register your new app: Edit  your_project_name/settings/base.py
     
    ```python
    #... 
    INSTALLED_APPS = [
        #...
        'ensembl.production.dbcopy',
        #...
    ]
    ```

    2.3 Check: 
       
    ```shell script 
    ./manage.py check 
   ```
 
