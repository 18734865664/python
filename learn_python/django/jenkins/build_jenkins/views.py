from django.shortcuts import render
from django.conf import settings

# Create your views here.
from django.http import HttpResponseRedirect ,HttpResponse ,StreamingHttpResponse
import subprocess
from initial_mysql.update_mysql import updateMysql
import pymysql
from django.views.decorators.csrf import csrf_exempt 
import urllib.parse
import urllib.request
import json
import queue
import threading
import time

return_info = {}
global exitFlag
exitFlag = {}


# 线程池，继承threading.Thread
class jenkinsBuildJobThread(threading.Thread):

    def __init__(self, timestamp, job_name_queue, jenkins_obj_name):
        threading.Thread.__init__(self)
        self.timestamp = timestamp
        self.job_name_queue = job_name_queue
        self.jenkins_obj_name = jenkins_obj_name
    # 重写run方法，线程启动时调用
    def run(self):
       build_job(self.job_name_queue, self.timestamp, self.jenkins_obj_name)
 
# 线程池，继承threading.Thread
class jenkinsJobThread(threading.Thread):

    def __init__(self, q, request):
        threading.Thread.__init__(self)
        self.q = q
        self.request = request
    # 重写run方法，线程启动时调用
    def run(self):
        series_thread(self.q, self.request)


@csrf_exempt
def build(request):
    # 初始化job_args表
    # obj = updateMysql()
    # obj.create_job_args_table()
    lock = threading.Lock()
    
    # 接收request请求
    if request.method == "GET":
        return HttpResponseRedirect("/build_jenkins/") 
    
    elif request.method == "POST":
        # print("收到post请求")
        jenkins_obj = request.POST['jenkins_obj']
        # timestamp = request.POST['timestamp']
        data = json.loads(jenkins_obj)
        # 创建队列
        try:
            queue_name = "queue" + "_" + data["jenkins_obj_name"]
            queue_name = queue.Queue(10)
        except:
            print("队列已存在")
        jobs = []
        # 创建线程池
        for thread_id in range(1,2):
            thread = jenkinsJobThread(queue_name, request)
            thread.start()
            jobs.append(thread)

        # 填充队列
        lock.acquire()
        queue_name.put(data)
        lock.release()
        
        
        for t in jobs:
            t.join()
        return_json = json.dumps(return_info[data["jenkins_obj_name"]]) 
        return HttpResponse(return_json, content_type="application/json")
        
        

def series_thread(q, request):
    lock_test = threading.Lock()
    data = q.get()
    # 从数据库中查询套餐对应应用列表
    db = pymysql.connect(host = settings.MYSQL_HOST, user = settings.MYSQL_USER, passwd = settings.MYSQL_PASS, port = int(settings.MYSQL_PORT))
    cursor = db.cursor() 
    sql = 'select jenkins_obj_member from jenkins_info.jenkins_obj where jenkins_obj_name = \"{}\"'.format(data["jenkins_obj_name"])
    cursor.execute(sql)
    jenkins_build_list_tmp = cursor.fetchall()[0][0]
    db.commit()
    db.close()
    try:
        jenkins_build_list = jenkins_build_list_tmp.split(',')
    except:
        jenkins_build_list = jenkins_build_list_tmp.split() 
   
    exitFlag[data["jenkins_obj_name"]] = len(jenkins_build_list)
    print(exitFlag[data["jenkins_obj_name"]])
    # 创建队列
    build_job_name_queue = queue.Queue(len(jenkins_build_list))
    # import pdb; pdb.set_trace()
    threads = []

    # 创建线程池
    for thread_id in range(1,4):
        thread = jenkinsBuildJobThread(data["timestamp"], build_job_name_queue, data["jenkins_obj_name"])
        thread.start()
        threads.append(thread)
    return_info[data["jenkins_obj_name"]] = {}
        
    # 填充队列
    lock_test.acquire()
    for build_job_name in jenkins_build_list:
        build_job_name_queue.put(build_job_name)
    lock_test.release()
        
    # 如果队列不为空，阻塞
    while not build_job_name_queue.empty():
        print("build_job_name_queue: " + str(build_job_name_queue.qsize()))
        time.sleep(1)
        pass
   
    # exitFlag是一个全局参数，声明，作为退出标识
    # global exitFlag;

    # 阻塞至进程停止
    for t in threads:
        t.join()

    # return_json = json.dumps(return_info[data["jenkins_obj_name"]]) 
    # exitFlag = 0
    # import pdb; pdb.set_trace()
    # return HttpResponse(return_json, content_type="application/json")
    # return return_json
    print(return_info[data["jenkins_obj_name"]])


def build_job(job_name_queue, timestamp, jenkins_obj_name):

    """
        接收一个jenkins的job列表，和一个时间戳。
        执行具体的构建触发动作，并返回查询服务的id

    """
    while True:
        # 监听工作队列
        if not job_name_queue.empty():
            build_job_name = job_name_queue.get()
            db = pymysql.connect(host = settings.MYSQL_HOST, user = settings.MYSQL_USER, passwd = settings.MYSQL_PASS, port = int(settings.MYSQL_PORT))
            cursor = db.cursor() 
            sql_build_args = "select * from jenkins_info.job_args where job_name = \"{}\"".format(build_job_name.replace('-', '_'))
            cursor.execute(sql_build_args)
            build_args = list(cursor.fetchall()[0])
            db.commit()
            db.close()
            url = settings.JENKINS_URL + build_args[0] + "/buildWithParameters"     
            data = {
                "branch_parents": build_args[2],
                "ftp_path": build_args[3],
                "mvn_args": build_args[4],
                "subitems": build_args[5],
                "next_build_num": int(build_args[6]) + 1
            }

            # 初始化参数表后，默认ftp_path是当天的目录，如果传入参数中上线时间不为空，则替换该参数
            if timestamp:
                data["ftp_path"] = data["ftp_path"].split("_v0.0_")[0] + "_v0.0_" + str(timestamp)
            return_info[jenkins_obj_name][build_job_name] = int(build_args[6]) + 1
            data_tmp = ''

            # 拼接触发job使用的参数列表
            for i in data.keys():
                if data_tmp:
                    data_tmp = data_tmp + '&' + i + '=' + str(data[i])
                else:
                    data_tmp = data_tmp + i + '=' + str(data[i])

            subprocess.call(["curl -X  POST http://jenkins:jenkins@10.100.140.161:8080/job/{}/buildWithParameters -d \"{}\"".format(build_job_name, data_tmp)], shell=True)
          
            # 阻塞，判断build是否完成
            while True:
                db = pymysql.connect(host = settings.MYSQL_HOST, user = settings.MYSQL_USER, passwd = settings.MYSQL_PASS, port = int(settings.MYSQL_PORT))
                cursor = db.cursor() 
                sql_build_args = "select count(*) from jenkins_info.job_result where job_name_build_id = \"{}\"".format(build_job_name.replace('-', '_') + '-' + str(data["next_build_num"]))
                cursor.execute(sql_build_args)
                build_count = int(cursor.fetchall()[0][0])
                db.commit()
                db.close()
                # print("======================================")
                print(exitFlag[jenkins_obj_name])
                if build_count > 0:
                    break
                else:
                    time.sleep(1)
            exitFlag[jenkins_obj_name] = exitFlag[jenkins_obj_name] - 1
        if exitFlag[jenkins_obj_name] == 0:
            break
        time.sleep(1)
        print("world")
 
