Ensembl Django project template
=================================

Ensembl Django project template

Quick start
-----------

1. Create a project

```shell script
django-admin startproject --template=https://github.com/ensembl/ensembl-dj-project/archive/main.zip --extension=py,env,example [your_project_name]

cd your_project_name
mv .env.example .env
pip install -r requirements.txt

# Check everything is in place with 
./manage.py check
# Should output 
```


2. Create an app within your project

    2.1 Init your app
    
    ```shell script
    cd your_project_name # if not already in project dir from previous step
    django-admin startapp --template=https://github.com/ensembl/ensembl-dj-app/archive/main.zip [your_app_name]

    ```

    2.2 Register your new app: Edit  your_project_name/settings/base.py
     
    ```python
    #... 
    INSTALLED_APPS = [
        #...
        [your_app_name]
        #...
    ]
    ```

    2.3 Check: 
       
    ```shell script 
    ./manage.py check 
   ```
 
