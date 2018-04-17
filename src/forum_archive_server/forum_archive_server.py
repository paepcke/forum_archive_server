#!/usr/bin/env python
# encoding: utf-8
'''
forum_archive_server.forum_archive_server -- shortdesc

forum_archive_server.forum_archive_server is a description

It defines classes_and_methods

@author:     user_name

@copyright:  2018 organization_name. All rights reserved.

@license:    license

@contact:    user_email
@deffield    updated: Updated
'''

import datetime
import getpass
import os
import socket
import sys
import traceback

from pymysql_utils.pymysql_utils import MySQLDB
from tornado import template
import tornado;
from tornado.httpclient import AsyncHTTPClient
from tornado.web import RequestHandler, asynchronous


DEBUG = 1

RESULT_TEMPLATE = template.Loader(os.path.dirname(__file__)).load("responseTemplate.html")

class ForumArchiveServer(RequestHandler):

    LOG_LEVEL_NONE  = 0
    LOG_LEVEL_ERR   = 1
    LOG_LEVEL_INFO  = 2
    LOG_LEVEL_DEBUG = 3

    LEGAL_REQUESTS = ['getFaqs']

    def __init__(self, tornadoWebAppObj, httpServerRequest):
        '''
        Invoked every time a request arrives.
        tornadoWebAppObj is not used.
        
        The httpServerRequest 
           HTTPServerRequest(protocol='http', host='localhost:8080', method='GET', uri='/serveFaqs', version='HTTP/1.1', remote_ip='::1')
        has constants/methods:
            .query            # what's after the ? in the URL
            .headers.keys()   # ['Accept-Language', 
                                 'Accept-Encoding', 
                                 'Connection', 
                                 'Accept', 
                                 'User-Agent', 
                                 'Dnt', 
                                 'Host', 
                                 'Upgrade-Insecure-Requests']
                    
        
        @param tornadoWebAppObj: unused
        @type tornadoWebAppObj: tornado.web.Application
        @param httpServerRequest: HTTPServerRequest object
        @type httpServerRequest: HTTPServerRequest
        '''
        super(ForumArchiveServer, self).__init__(tornadoWebAppObj, httpServerRequest)
        self.loglevel = ForumArchiveServer.LOG_LEVEL_DEBUG
        #self.loglevel = CourseCSVServer.LOG_LEVEL_INFO
        #self.loglevel = CourseCSVServer.LOG_LEVEL_NONE
        
        self.testing = False
        
    @asynchronous
    def get(self):
        http_client  = AsyncHTTPClient()
        request_dict = self.request.arguments
        
        self.serveOneForumRequest(request_dict, http_client)
        self.finish()
        http_client.close()    

    def logInfo(self, msg):
        if self.loglevel >= ForumArchiveServer.LOG_LEVEL_INFO:
            print(str(datetime.datetime.now()) + ' info: ' + msg)

    def logErr(self, msg):
        if self.loglevel >= ForumArchiveServer.LOG_LEVEL_ERR:
            print(str(datetime.datetime.now()) + ' error: ' + msg)

    def logDebug(self, msg):
        if self.loglevel >= ForumArchiveServer.LOG_LEVEL_DEBUG:
            print(str(datetime.datetime.now()) + ' debug: ' + msg)

    def serveOneForumRequest(self, request_dict, http_client):

        if self.testing:
            self.currUser  = 'unittest'
            self.defaultDb = 'unittest'
        else:
            self.currUser  = getpass.getuser()
            self.defaultDb = 'ForumArchive'

        self.dbError = 'no error'
        if self.ensureOpenMySQLDb() is None:
            self.writeError("Error opening database: '%s'" % self.dbError)
            return
        # Get the request name:
        try:
            try:
                requestName = request_dict['req'][0]
            except KeyError as e:
                badRequest = e.args[0]
                self.writeError("Bad or missing request argument: %s" % badRequest)
                return
            except Exception as e:
                self.writeError("Bad request part of URL: '%s'" % request_dict)
                return
            if requestName not in self.LEGAL_REQUESTS:
                self.writeError("Request '%s' is not one of %s" % (request_dict, self.LEGAL_REQUESTS))
                return   
            
            # Caller wants list of course names?
            if requestName == 'getFaqs':
                # For FAQ entry requests, args is a list of 
                # keywords:
                try:
                    keywords = request_dict['keyword']
                except KeyError as e:
                    self.writeError("Requested getFaqs without providing keyword request entry.")
                    return
                if len(keywords) == 0:
                    self.writeError("Requested getFaqs without providing keywords.")
                    return
                self.handleFaqLookup(keywords)
                return
        except Exception as e:
            if self.loglevel == ForumArchiveServer.LOG_LEVEL_NONE:
                return
            elif self.loglevel == ForumArchiveServer.LOG_LEVEL_INFO:
                self.logErr('Error while processing req: %s' % `e`)
            elif self.loglevel == ForumArchiveServer.LOG_LEVEL_DEBUG:
                self.logErr('Error while processing req: %s' % str(traceback.print_exc()))
            self.writeError("%s" % `e`)
        finally:
            try:
                if self.mysqlDb is not None:
                    self.mysqlDb.close()
            except Exception as e:
                self.writeError("Error during MySQL driver close: '%s'" % `e`)

    def handleFaqLookup(self, keywords):
        query = '''SELECT question, answer, question_id
    				 FROM ForumKeywords LEFT JOIN ForumPosts
    				 ON question_id = id
    				 WHERE keyword = '%s'
    				 ORDER BY answer_type DESC,
    				          unique_views DESC,
    				          total_no_upvotes DESC;
                     ''' % keywords[0]
        if len(keywords) == 1:
            query += ';'
        else: 
            for keyword in keywords[1:]:
                query += " OR keyword = '%s'" % keyword
            query += ';'
        
        for result in self.mysqlDb.query(query):
            # Format the list of tuples, and send
            # back to browser. Each result will
            # be a tuple: (<questionText>,<answerText>,<questionId>)
            self.writeResult(result, keywords)

    def ensureOpenMySQLDb(self):
        try:
            home_dir = os.path.expanduser('~')
            with open(os.path.join(home_dir, '.ssh/mysql'), 'r') as fd:
                self.mySQLPwd = fd.readline().strip()
                self.mysqlDb = MySQLDB(user=self.currUser, passwd=self.mySQLPwd, db=self.defaultDb)
        except Exception:
            try:
                # Try w/o a pwd:
                self.mySQLPwd = None
                self.mysqlDb = MySQLDB(user=self.currUser, db=self.defaultDb)
            except Exception as e:
                # Remember the error msg for later:
                self.dbError = `e`;
                self.mysqlDb = None
        return self.mysqlDb


    def writeResult(self, resultTuple, keywords):
        '''
        Result tuples are (<questionText>, answerText, questionID).
        Keywords is an array of keywords that are were requested from
        the browser. The questionText/answerText are placed in the
        Tornado Web template, which is then sent to the browser. 
        The questionID and keywords are used for logging.
        
        @param resultTuple: Result from query to MySQL
        @type resultTuple: (string,string,string)
        @param keywords: The keyword(s) passed from the browser.
        @type keywords: [string]
        '''

        self.logDebug("Response: %s: %s" % (keywords, resultTuple[2]))
        if not self.testing:
            (question, answer) = (resultTuple[0], resultTuple[1])
            self.write(RESULT_TEMPLATE.generate(question=question, answer=answer))

    def writeError(self, msg):
        '''
        Writes a response to the JS running in the browser
        that indicates an error. Result action is "error",
        and "args" is the error message string:

        :param msg: error message to send to browser
        :type msg: String
        '''
        self.logDebug("Sending err to browser: %s" % msg)
        if not self.testing:
            try:
                self.write(msg)
            except IOError as e:
                self.logErr('IOError while writing error to browser; msg attempted to write; "%s" (%s)' % (msg, `e`))



def main(argv=None):
    '''Command line options.'''

    if argv is None:
        argv = sys.argv[1:]
    try:

        # MAIN BODY #
        application = tornado.web.Application([(r"/serveFaqs", ForumArchiveServer),
                                               (r"/css/(.*)", tornado.web.StaticFileHandler, {"path": "./css"},),
                                               ])
    
        # To find the SSL certificate location, we assume
        # that it is stored in dir '.ssl' in the current
        # user's home dir.
        # We'll build string up to, and excl. '.crt'/'.key' in (for example):
        #     "/home/paepcke/.ssl/mono.stanford.edu.crt"
        # and "/home/paepcke/.ssl/mono.stanford.edu.key"
        # The home dir and fully qual. domain name
        # will vary by the machine this code runs on:
        # We assume the cert and key files are called
        # <fqdn>.crt and <fqdn>.key:
    
        homeDir = os.path.expanduser("~")
        thisFQDN = socket.getfqdn()
    
        sslRoot = '%s/.ssl/%s' % (homeDir, thisFQDN)
        #*********
        # For self signed certificate:
        #sslRoot = '/home/paepcke/.ssl/server'
        #*********
    
        sslArgsDict = {
         #******"certfile": sslRoot + '_stanford_edu_cert.cer',
         "certfile": os.path.join(homeDir, '.ssl/Taffy', 'taffy_stanford_edu_cert.cer'),
         #******"keyfile":  sslRoot + '.stanford.edu.key',
         "keyfile":  os.path.join(homeDir, '.ssl/Taffy', 'taffy.stanford.edu.key')
         }
    
        #******http_server = tornado.httpserver.HTTPServer(application,ssl_options=sslArgsDict)
        http_server = tornado.httpserver.HTTPServer(application) #@UnusedVariable
    
        #******application.listen(8080, ssl_options=sslArgsDict)
        application.listen(8080)
    
        sys.stdout.write('Starting ForumArchiveServer.')
        try:
            tornado.ioloop.IOLoop.instance().start()
        except Exception as e:
            print("Error inside Tornado ioloop; continuing: %s" % `e`)
                
    
    except Exception, e:
        sys.stderr.write('Could not start ForumArchiveServer.')
        return 2


if __name__ == "__main__":

    sys.exit(main())
