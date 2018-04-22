#!/usr/bin/env python
# encoding: utf-8
'''
Server to return forum question/answer pairs from
either search or wordclouds. Uses Tornado to manage
incoming connections. 

@author:     Andreas Paepcke

'''

import datetime
import getpass
import os
import socket
import sys
import traceback
import uuid
import urllib

from pymysql_utils.pymysql_utils import MySQLDB
from tornado import template
import tornado;
from tornado.httpclient import AsyncHTTPClient
from tornado.web import RequestHandler, asynchronous

DEBUG = 1

RESULT_TEMPLATE = template.Loader(os.path.dirname(__file__)).load("responseTemplate.html")

class ForumArchiveServer(RequestHandler):

    # =========================== Constants ==================
    LOG_LEVEL_NONE  = 0
    LOG_LEVEL_ERR   = 1
    LOG_LEVEL_INFO  = 2    
    LOG_LEVEL_DEBUG = 3

    LEGAL_REQUESTS = ['getFaqs', 'demo']
    
    RESULT_WEB_PAGE_HEADER = '''
        <!DOCTYPE html>
    				  <html>            
    				    <head>
                        <script src="https://cdn.rawgit.com/google/code-prettify/master/loader/run_prettify.js?lang=python&amp;skin=sunburst"></script>
    				      <meta charset="utf-8">
    				      <meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1">
    				      <title>From the Forum Archives</title>
    				      <meta content='Forum Questions and Answers' name='description' />
    				      <meta content='width=device-width, initial-scale=1' name='viewport' />
    				      <link rel="stylesheet" href="/css/forumArchiveStyle.css" />
    				    </head>
    				    <body>
		'''
    RESULT_WEB_PAGE_JS_AND_FOOTER = ''' 
        <script type="text/javascript">
          var feedbackForms = document.getElementsByClassName('line-item-feedback')
          for (var i=0; i<feedbackForms.length; i++) {
              // feedbackForms[i].onclick = feedbackForms[i].submit;
              feedbackForms[i].onclick = function(event) {
                  var host     = window.location.hostname;  // myserver.myuniversity.edu
                  var port     = window.location.port;      // 8080
                  var protocol = window.location.protocol;  // http:
                  var pathname = window.location.pathname;  // /serveFaqs
                  var params   = "?feedback=''&value=" + event.target.value;
                                           
                  // alert(protocol + '//' + host + ':' + port + pathname + params);
                  if (typeof event.target.value != 'undefined') {
                     fetch(protocol + '//' + host + ':' + port + pathname + params)
                  }
              }
          }
        </script>
        </body>
        </html>
        '''

    ERR_HTML_PAGE = '''
        <html>
        <page>
        Sadly, an error occurred at the server.<br>
        please <a href="mailto:ankitab@stanford.edu?cc=paepcke@cs.stanford.edu&subject=Forum+Server+Error&body=%s">
           click this link to send email to Ankita</a>for debugging. Thanks!
        </page>
        </html>
        '''

    # =============================== Methods ========================
    
    #-----------------------
    # Constructor
    #---------------
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
    
    #-----------------------
    # get() 
    #---------------
        
    @asynchronous
    def get(self):
        '''
        Called by Tornado when HTTP GET request
        arrives. Arguments part of URL is in 
        self.request.arguments.

        '''
        http_client  = AsyncHTTPClient()
        request_dict = self.request.arguments
        
        # Is this a request for a keyword lookup,
        # or feedback from a form in a prior response
        # page?
        
        if request_dict.get('req', None) is not None:
            self.serveOneForumRequest(request_dict, http_client)
        elif request_dict.get('feedback', None) is not None:
            self.logFeedback(request_dict)
        else:
            msg = "Bad request: %s" % request_dict
            self.logErr(msg)
            self.writeError(msg)
            
        self.finish()
        http_client.close()    

    #-----------------------
    # logInfo() 
    #---------------

    def logInfo(self, msg):
        if self.loglevel >= ForumArchiveServer.LOG_LEVEL_INFO:
            sys.stdout.write(str(datetime.datetime.now()) + ' info: ' + msg + '\n')
            sys.stdout.flush()

    #-----------------------
    # logErr() 
    #---------------

    def logErr(self, msg):
        if self.loglevel >= ForumArchiveServer.LOG_LEVEL_ERR:
            sys.stderr.write(str(datetime.datetime.now()) + ' error: ' + msg + '\n')
            sys.stderr.flush()

    #-----------------------
    # logDebug() 
    #---------------

    def logDebug(self, msg):
        if self.loglevel >= ForumArchiveServer.LOG_LEVEL_DEBUG:
            sys.stdout.write(str(datetime.datetime.now()) + ' debug: ' + msg + '\n')
            sys.stdout.flush()

    #-----------------------
    # logFeedback() 
    #---------------

    def logFeedback(self, request_dict):
        '''
        Given args part of incoming URL, from 
        student clicking one of the feedback survey
        radio buttons: logs the user's UID, the clicked 
        radio button's name (Not/Partial/Complete), session ID,
        and answer rank whose survey was clicked. Rank 
        is same as number of entry in viewing order.  
        
        @param request_dict: URL argument part
        @type request_dict: dict
        '''
        # The [0] pulls the info in 
        #   ['Partial,040c8977-e040-4b87-bcc0-b899cdcd093c,1']
        # out of the parens to make the log simple:
        
        self.logInfo("Feedback: %s" % str(request_dict['value'][0]))
        
    def serveOneForumRequest(self, request_dict, http_client):
        '''
        Responsible for asychnonously serving the HTTP request
        on one connection. THe connection remains open.
        
        @param request_dict: args part of URL
        @type request_dict: dict
        @param http_client: Tornado http client object
        @type http_client: AsyncHTTPClient
        '''

        # Unittests not implemented:
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
            
            # What does the student want?
            if requestName in ['getFaqs', 'demo']:
                # For FAQ entry requests, args is a list of 
                # keywords:
                try:
                    keywords = request_dict['keyword']
                except KeyError as e:
                    self.writeError("Requested getFaqs without providing keyword request entry.")
                    return
                # Get the user id:
                try:
                    uid = request_dict['uid']
                except KeyError as e:
                    self.writeError("Requested getFaqs without providing user id entry.")
                    return
                if len(keywords) == 0:
                    self.writeError("Requested getFaqs without providing keywords.")
                    return
                if len(uid) == 0:
                    self.writeError("Requested getFaqs with empty uid.")
                    return
                self.handleFaqLookup(keywords, requestName == 'demo', uid[0])
                return
            else:
                self.logDebug("Unknown request: %s" % requestName)
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

    def handleFaqLookup(self, keywords, isDemo, uid):
        query = '''SELECT question, answer, question_id
    				 FROM ForumKeywords LEFT JOIN ForumPosts
    				 ON question_id = id
                                 WHERE LOCATE('%s', keyword) > 0
                     ''' % keywords[0]
        if len(keywords) > 1:
            for keyword in keywords[1:]:
                query += " OR keyword = '%s'" % keyword
            
        query += ''' 
                     ORDER BY answer_type DESC,
    				          unique_views DESC,
    				          total_no_upvotes DESC;
    			'''
        # Create a unique session ID unless running in demo mode:
        session_id = 'demo' if isDemo else str(uuid.uuid4())    
        rank = 0
        results = self.mysqlDb.query(query)

        web_page = self.startResultWebPage(keywords)
        for result in results:
            # Format the list of tuples, and send
            # back to browser. Each result will
            # be a tuple: (<questionText>,<answerText>,<questionId>)
            rank += 1
            web_page = self.addWebResult(web_page, result, keywords, rank, session_id, uid)
        self.writeResult(web_page)

    def startResultWebPage(self, keywords):
        '''
        Starts return Web page for a forum archive request.
        Doctype, head contents, and body open tag.

        @param keywords: keywords that led to this result: for result page title.
        @type keywords: str
        @return: Web page fragment
        @rtype: str
        '''
        self.response_records = []
        header = ForumArchiveServer.RESULT_WEB_PAGE_HEADER +\
            '<div class="title">Keyword(s): %s' % ','.join(keywords) +\
            '  <div class="feedback_email">' +\
            '    <a href="mailto:ankitab@stanford.edu?subject=Forum%20Archive%20Feedback&cc=paepcke@cs.stanford.edu">' +\
            '       Feedback to Ankita' +\
            '    </a></div>\n' +\
            '</div>\n'
        return header
        
    def addWebResult(self, web_page, resultTuple, keywords, rank, session_id, uid):
        '''
        Result tuples are (<questionText>, answerText, questionID).
        Keywords is an array of keywords that are were requested from
        the browser. The questionText/answerText are placed in the
        Tornado Web template, which is then sent to the browser. 
        The questionID and keywords are used for logging.
        
        Adds the keyword, qid, rank, and session_id to the accumulating
        log string. Does not write it out. That's done in writeResult()
        
        @param web_page: Web page constructed so far
        @type web_page: str
        @param resultTuple: Result from query to MySQL
        @type resultTuple: (string,string,string)
        @param keywords: The keyword(s) passed from the browser.
        @type keywords: [string]
        @param rank: Rank of this result in the session
        @type rank: int
        @param session_id: unique id used in log to know the answers
                 that were given in response to a single request.
        @type session_id: string
        @param uid: user ID created by browser or retrieved there from cookie.
        @type uid: string
        @return: web page fragment with HTML for one question/answer result added
        @rtype: str 
        '''

        # Turn the keywords array and rank integer into strings
        # to make final log string construction easier
        # in writeResult(). resultTuple[2] is the question ID:
        self.response_records.append([str(keywords), resultTuple[2], session_id, str(rank), uid])
        
        if not self.testing:
            (question, answer) = (resultTuple[0], resultTuple[1])
            question = "<pre class=\"prettyprint\">" + question + "</pre>"
            answer = "<pre class=\"prettyprint\">" + answer + "</pre>"
            web_page += RESULT_TEMPLATE.generate(question=question, 
                                                 answer=answer,
                                                 session_id=session_id,
                                                 rank=rank,
                                                 uid=uid
                                                )
            return web_page
        
    def writeResult(self, web_page):
        '''
        Given a web page fragment with head, and all HTML for
        each keyword-matching result, add Javascript and closing
        body/html tags. Write the result back to the browser.
        
        Also: writes all the responses too the log: keyword, qid, 
        rank, and session_id. 
        
        @param web_page: web page fragment
        @type web_page: str
        '''
        # The self.response_records is an array of arrays:
        #
        #   a = []
        #   a.append(['foo','bar','fum'])
        #   a.append(['blue','green','yellow'])
        # ==> [['foo', 'bar', 'fum'], ['blue', 'green', 'yellow']]
        #
        # Turn that into: 'foo,bar,fum\n   blue,green,yellow'

        response_log_str = '\n   ' + '\n   '.join([','.join(one_record) for one_record in self.response_records])
        self.logInfo(response_log_str)
        web_page += ForumArchiveServer.RESULT_WEB_PAGE_JS_AND_FOOTER
        self.write(web_page)
        
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
                self.write(ForumArchiveServer.ERR_HTML_PAGE % (urllib.quote(msg)) + '\n')
                self.flush()
                # self.write(msg)
            except IOError as e:
                self.logErr('IOError while writing error to browser; msg attempted to write; "%s" (%s)' % (msg, `e`))

    def ensureOpenMySQLDb(self):
        '''
        Finds MySQL password in ~/.ssh, and opens the MySQL db.
        '''
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

#**********
# class LandingPageServer(tornado.web.RequestHandler):
#     def get(self):
#         self.w
#**********

# ====================================  Main ================

def main(argv=None):
    '''Command line options.'''

    if argv is None:
        argv = sys.argv[1:]
    try:

        # MAIN BODY #
        application = tornado.web.Application([(r"/serveFaqs", ForumArchiveServer),
                                               (r"/css/(.*)", tornado.web.StaticFileHandler, {"path": "./css"},),
                                               (r"/wordclouds/(.*)", tornado.web.StaticFileHandler, {"path": "./wordclouds"},),
                                               (r"/(.*)", tornado.web.StaticFileHandler, 
                                                        {"path": "./", "default_filename": "index.html"},),
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
    
        ## The ugly commented code below is for SSL operation if ever neccesary.
        
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
    
        sys.stdout.write('Starting ForumArchiveServer.\n')
        try:
            tornado.ioloop.IOLoop.instance().start()
        except Exception as e:
            print("Error inside Tornado ioloop; continuing: %s" % `e`)
                
    
    except Exception, e:
        sys.stderr.write('Could not start ForumArchiveServer.')
        return 2


if __name__ == "__main__":

    sys.exit(main())
