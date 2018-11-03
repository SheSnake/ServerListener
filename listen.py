import subprocess
import time
import smtplib
import json
import arrow
from email.mime.text import MIMEText
from email.header import Header


def get_tcp_connection():
    cmd = 'netstat|grep tcp|awk \'{print $4,$5,$6}\''
    res = subprocess.getoutput(cmd).split('\n')
    return res

class EmailSender(object):
    def __init__(self, user, pwd, mail_host):
        self.user = user
        self.pwd = pwd
        self.mail_host = mail_host

    def send(self, content, receiver):
        try:
            message = MIMEText(content, 'html', 'utf-8')
            message['From'] = self.user
            message['To'] =  receiver
            message['Subject'] = Header('User Connect To Server', 'utf-8')
            smtpObj = smtplib.SMTP_SSL(self.mail_host, 465)
            res = smtpObj.login(self.user, self.pwd)
            res = smtpObj.sendmail(self.user, receiver, message.as_string())
            return True
        except smtplib.SMTPException as e:
            print('error {}'.format(e))
            return False
        except Exception as e:
            print('other error {}'.format(e))
            return False


class ServerListen(object):
    def __init__(self, email_user, email_pwd, email_host, receiver, services):
        self.server = dict()
        self.port_map = dict()
        self.suspect_connect = dict()

        for k,v in services.items():
            self.server[k] = set()
            self.port_map[v] = k
            self.port_map[k] = k
            self.suspect_connect[k] = dict()

        self.email_sender = EmailSender(email_user, email_pwd, email_host)
        self.receiver = receiver

    def poll(self):
        conns = get_tcp_connection()
        current_client = dict()
        for k in self.server:
            current_client[k] = set()

        # del suspect connect expire
        need_del = set()
        for k,v in self.suspect_connect.items():
            for host,times in v.items():
                now = arrow.utcnow().timestamp
                if now - self.suspect_connect[k][host][-1] > 60*3:
                    need_del.add((k,host))

        for (k, host) in need_del: 
            del self.suspect_connect[k][host]
            print('del suspect {} {}'.format(k, host))

        # update conn info
        for conn in conns:
            server, user, status = conn.split(' ')
            server_port = server.split(':')[-1]
            user_host = user.split(':')[0]
            if status != 'ESTABLISHED': continue
            if server_port in self.port_map:
                server_name = self.port_map[server_port]
                if user_host in self.server[server_name]: 
                    current_client[server_name].add(user_host)
                elif user_host in self.suspect_connect[server_name]:
                    now = arrow.utcnow().timestamp
                    if len(self.suspect_connect[server_name][user_host]) >= 30*2:
                        # new confirm connect
                        self.notify(server, server_name, user, status)
                        current_client[server_name].add(user_host)
                        del self.suspect_connect[server_name][user_host]
                    else:
                        # new suspect connect
                        self.suspect_connect[server_name][user_host].append(now)
                else:
                    # suspect connect
                    self.suspect_connect[server_name][user_host] = [arrow.utcnow().timestamp]
                    print('suspect connect {} {}'.format(server, user))

        for k in self.server:
            self.server[k] = current_client[k]

        print(self.server)
        time.sleep(2)
        self.poll()


    def notify(self, server, sn, user, status):
        msg = '<p>Service: {}({})</p> <p>New Connected By: {}</p> <p>Time: {}</p>'.format(server, sn, user, arrow.utcnow())
        self.email_sender.send(msg, self.receiver)
        print('send msg:{}'.format(msg))


                


if __name__ == '__main__':
    config = json.loads(open('config.json', 'r').read())
    listener = ServerListen(**config)
    listener.poll()


