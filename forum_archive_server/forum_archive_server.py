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
import json
from optparse import OptionParser
import os
import socket
import sys
import threading
import traceback

from pymysql_utils.pymysql_utils import MySQLDB
import tornado;
from tornado.httpserver import HTTPServer;
from tornado.ioloop import IOLoop;
from tornado.websocket import WebSocketHandler;
from IPython.utils.path import HomeDirError


__all__ = []
__version__ = 0.1
__date__ = '2018-04-12'
__updated__ = '2018-04-12'

DEBUG = 1
TESTRUN = 0
PROFILE = 0

class ForumArchiveServer(WebSocketHandler):

    LOG_LEVEL_NONE  = 0
    LOG_LEVEL_ERR   = 1
    LOG_LEVEL_INFO  = 2
    LOG_LEVEL_DEBUG = 3

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
        
    def allow_draft76(self):
        '''
        Allow WebSocket connections via the old Draft-76 protocol. It has some
        security issues, and was replaced. However, Safari (i.e. e.g. iPad)
        don't implement the new protocols yet. Overriding this method, and
        returning True will allow those connections.
        '''
        return True

    def open(self): #@ReservedAssignment
        '''
        Called by WebSocket/tornado when a client connects. Method must
        be named 'open'
        '''
        self.logDebug("Open called")

    def get(self):
        #print 'URL args: %s' % self.request.arguments

        serverThread = DataServer(self.request.arguments, self, self.testing)
        serverThread.start()
        # If we are testing the unittest needs to wait
        # for the thread to finish, so that results can
        # be checked. During production ops we return
        # to the Tornado main loop as quickly as we can.
        if self.testing:
            serverThread.join()
        
        
    def on_message(self, message):
        '''
        Connected browser requests action: "<actionType>:<actionArg(s)>,
        where actionArgs is a single string or an array of items.

        :param message: message arriving from the browser
        :type message: string
        '''
        #print message
        try:
            requestDict = json.loads(message)
            self.logInfo("request received: %s" % str(message))
        except Exception as e:
            self.writeError("Bad JSON in request received at server: %s" % `e`)

        serverThread = DataServer(requestDict, self, self.testing)
        serverThread.start()
        # If we are testing the unittest needs to wait
        # for the thread to finish, so that results can
        # be checked. During production ops we return
        # to the Tornado main loop as quickly as we can.
        if self.testing:
            serverThread.join()

    def logInfo(self, msg):
        if self.loglevel >= ForumArchiveServer.LOG_LEVEL_INFO:
            print(str(datetime.datetime.now()) + ' info: ' + msg)

    def logErr(self, msg):
        if self.loglevel >= ForumArchiveServer.LOG_LEVEL_ERR:
            print(str(datetime.datetime.now()) + ' error: ' + msg)

    def logDebug(self, msg):
        if self.loglevel >= ForumArchiveServer.LOG_LEVEL_DEBUG:
            print(str(datetime.datetime.now()) + ' debug: ' + msg)


class DataServer(threading.Thread):

    def __init__(self, requestDict, mainThread, testing=False):

        threading.Thread.__init__(self)

        self.mainThread = mainThread
        self.testing = testing


        if testing:
            self.currUser  = 'unittest'
            self.defaultDb = 'unittest'
        else:
            self.currUser  = getpass.getuser()
            self.defaultDb = 'ForumArchive'

        self.ensureOpenMySQLDb()

        # Locate the makeCourseCSV.sh script:
        self.thisScriptDir = os.path.dirname(__file__)
        self.exportCSVScript = os.path.join(self.thisScriptDir, '../scripts/makeCourseCSVs.sh')
        self.courseInfoScript = os.path.join(self.thisScriptDir, '../scripts/searchCourseDisplayNames.sh')
        self.exportForumScript = os.path.join(self.thisScriptDir, '../scripts/makeForumCSV.sh')
        self.exportEmailListScript = os.path.join(self.thisScriptDir, '../scripts/makeEmailListCSV.sh')

        # A dict into which the various exporting methods
        # below will place instances of tempfile.NamedTemporaryFile().
        # Those are used as comm buffers between shell scripts
        # and this Python code:
        self.infoTmpFiles = {}
        self.dbError = 'no error'
        self.requestDict = requestDict

        self.currTimer = None

    def ensureOpenMySQLDb(self):
        try:
            with open('/home/%s/.ssh/mysql' % self.currUser, 'r') as fd:
                self.mySQLPwd = fd.readline().strip()
                self.mysqlDb = MySQLDB(user=self.currUser, passwd=self.mySQLPwd, db=self.mainThread.defaultDb)
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

    def run(self):
        self.serveOneDataRequest(self.requestDict)

    def serveOneDataRequest(self, requestDict):
        # Get the request name:
        try:
            requestName = requestDict['req']
            args        = requestDict['args']

            if requestName == 'keepAlive':
                return

            # Caller wants list of course names?
            if requestName == 'getFaqs':
#                 #*********
#                 self.mainThread.logInfo('Sleep-and-loop')
#                 for i in range(10):
#                     time.sleep(1)
#                 self.mainThread.logInfo('Back to serving')
#                 #*********
                # For FAQ entry requests, args is a list of 
                # keywords:
                
                keywords = args.strip()
                self.handleFaqLookup(requestName, keywords)
                return
            # JavaScript at the browser 'helpfully' adds a newline
            # after course id that is checked by user. If the
            # arguments include a 'courseId' key, then strip its
            # value of any trailing newlines:
            try:
                courseId = args['courseId']
                args['courseId'] = courseId.strip()
                courseIdWasPresent = True
            except (KeyError, TypeError, AttributeError):
                # Arguments either doesn't have a courseId key
                # (KeyError), or args isn't a dict in the first
                # place; both legitimate requests:
                courseIdWasPresent = False
                pass

            courseList = None

            if requestName == 'getData':
                startTime = datetime.datetime.now()
                if courseIdWasPresent and (courseId == 'None' or courseId is None):
                    # Need list of all courses, b/c we'll do
                    # engagement analysis for all; use MySQL wildcard:
                    courseList = self.queryCourseNameList('%')

        except Exception as e:
            if self.mainThread.loglevel == ForumArchiveServer.LOG_LEVEL_NONE:
                return
            elif self.mainThread.loglevel == ForumArchiveServer.LOG_LEVEL_INFO:
                self.mainThread.logErr('Error while processing req: %s' % `e`)
            elif self.mainThread.loglevel == ForumArchiveServer.LOG_LEVEL_DEBUG:
                self.mainThread.logErr('Error while processing req: %s' % str(traceback.print_exc()))
            self.writeError("%s" % `e`)
        finally:
            try:
                self.mysqlDb.close()
            except Exception as e:
                self.writeError("Error during MySQL driver close: '%s'" % `e`)


def main(argv=None):
    '''Command line options.'''

    program_name = os.path.basename(sys.argv[0])
    program_version = "v0.1"
    program_build_date = "%s" % __updated__

    program_version_string = '%%prog %s (%s)' % (program_version, program_build_date)
    #program_usage = '''usage: spam two eggs''' # optional - will be autogenerated by optparse
    program_longdesc = '''''' # optional - give further explanation about what the program does
    program_license = "Copyright 2018 user_name (organization_name)                                            \
                Licensed under the Apache License 2.0\nhttp://www.apache.org/licenses/LICENSE-2.0"

    if argv is None:
        argv = sys.argv[1:]
    try:
        # setup option parser
        parser = OptionParser(version=program_version_string, epilog=program_longdesc, description=program_license)
        parser.add_option("-i", "--in", dest="infile", help="set input path [default: %default]", metavar="FILE")
        parser.add_option("-o", "--out", dest="outfile", help="set output path [default: %default]", metavar="FILE")
        parser.add_option("-v", "--verbose", dest="verbose", action="count", help="set verbosity level [default: %default]")

        # set defaults
        parser.set_defaults(outfile="./out.txt", infile="./in.txt")

        # process options
        (opts, args) = parser.parse_args(argv)

        if opts.verbose > 0:
            print("verbosity level = %d" % opts.verbose)
        if opts.infile:
            print("infile = %s" % opts.infile)
        if opts.outfile:
            print("outfile = %s" % opts.outfile)

        # MAIN BODY #
        application = tornado.web.Application([(r"/serveFaqs", ForumArchiveServer),])
        #application.listen(8080)
    
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
        http_server = tornado.httpserver.HTTPServer(application)
    
        #******application.listen(8080, ssl_options=sslArgsDict)
        application.listen(8080)
    
        try:
            tornado.ioloop.IOLoop.instance().start()
        except Exception as e:
            print("Error inside Tornado ioloop; continuing: %s" % `e`)
                
    
    except Exception, e:
        indent = len(program_name) * " "
        sys.stderr.write(program_name + ": " + repr(e) + "\n")
        sys.stderr.write(indent + "  for help use --help")
        return 2


if __name__ == "__main__":

    sys.exit(main())