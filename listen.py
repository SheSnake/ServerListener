import subprocess
import time
import smtplib
import json
import arrow
import asyncio
import logzero
from logzero import logger
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
            logger.error('error {}'.format(e))
            return False
        except Exception as e:
            logger.error('other error {}'.format(e))
            return False


class ServerListen(object):
    def __init__(self, email_user, email_pwd, email_host, receiver, services):
        self.server = dict()
        self.lost_client = dict()
        self.port_map = dict()
        self.suspect_connect = dict()
        self.loop = asyncio.new_event_loop()

        for k,v in services.items():
            self.server[k] = set()
            self.lost_client[k] = dict()
            self.port_map[v] = k
            self.port_map[k] = k
            self.suspect_connect[k] = dict()

        self.email_sender = EmailSender(email_user, email_pwd, email_host)
        self.receiver = receiver

    async def poll(self):
        conns = get_tcp_connection()
        current_client = dict()
        for k in self.server:
            current_client[k] = set()

        # del suspect connect expire
        need_del = set()
        for k,v in self.suspect_connect.items():
            for host,times in v.items():
                now = arrow.utcnow().timestamp
                if now - self.suspect_connect[k][host][-1] > 60 * 3:
                    need_del.add((k,host))

        for (k, host) in need_del: 
            del self.suspect_connect[k][host]
            logger.info('del suspect {} {}'.format(k, host))

        # update conn info
        for conn in conns:
            try:
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
                        if len(self.suspect_connect[server_name][user_host]) >= 12*2:
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
                        logger.info('suspect connect {} {}'.format(server, user))
            except Exception as e:
                msg = 'parser port info error, reason:{}, info:{}'.format(e, conn)
                logger.error(msg)

        for k,clients in self.server.items():
            for client in clients:
                if not (client in current_client[k]):
                    self.lost_client[k][client] = self.lost_client[k][client]+1 if client in self.lost_client[k] else 0
                else:
                    self.lost_client[k][client] = 0

                if  self.lost_client[k][client] > 30:
                    self.server[k].remove(client)

            self.server[k].update(current_client[k])

        logger.info({'client_status': self.lost_client})

        await asyncio.sleep(2)
        asyncio.ensure_future(self.poll(), loop=self.loop)

    def run(self):
        asyncio.ensure_future(self.poll(), loop=self.loop)
        self.loop.run_forever()



    def notify(self, server, sn, user, status):
        msg = '<p>Service: {}({})</p> <p>New Connected By: {}</p> <p>Time: {}</p>'.format(server, sn, user, arrow.utcnow())
        self.email_sender.send(msg, self.receiver)
        logger.info('send msg:{}'.format(msg))


                


if __name__ == '__main__':
    logzero.formatter(logzero.LogFormatter(
        fmt='%(color)s[%(levelname)1.1s %(asctime)s %(module)s:%(lineno)d]%(end_color)s %(message)s'
        )
    )
    config = json.loads(open('config.json', 'r').read())
    listener = ServerListen(**config)
    listener.run()


