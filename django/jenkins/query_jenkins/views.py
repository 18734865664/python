from django.shortcuts import render
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
import pymysql
import json

'''
接收调用方传入的 项目名+build_id
回传查询到的构建记录详情

'''

# Create your views here.

def test(request):
    return HttpResponse("hello")

@csrf_exempt
def query(request):
    if request.method == "POST":
        # import pdb; pdb.set_trace()
        query_obj = request.POST['job_obj']
        job_obj = json.loads(query_obj)
        job_name = job_obj["job_name"]
        build_id = job_obj["build_id"]
        job_name_build_id = job_name + "-" + str(build_id)

        db = pymysql.connect(host = settings.MYSQL_HOST, user = settings.MYSQL_USER, passwd = settings.MYSQL_PASS, port = int(settings.MYSQL_PORT))
        cursor = db.cursor() 
        sql = "select * from jenkins_info.job_result where job_name_build_id = '{}'".format(job_name_build_id)
        cursor.execute(sql)
        data = cursor.fetchall()[0]
        return_data = {
            "branches_path" : data[6],
            "mvn_args" : data[3],
            "mvn_build_result" : data[4],
            "mvn_failuer_result" : data[5],
            "docker_image_repository" : data[1],
            "docker_image_tag" : data[2],
            "ftp_path" : data[7],
        }
        return_json = json.dumps(return_data)
        return HttpResponse(return_json, content_type = "application/json") 
        
   

