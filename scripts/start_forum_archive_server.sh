#!/usr/bin/env bash


# Get directory in which this script is running,
# and relative to which its support scripts therefore live:

CURR_SCRIPTS_DIR="$( cd "$( dirname "${0}" )" && pwd )"

EXEC_DIR=${CURR_SCRIPTS_DIR}/../src/forum_archive_server
EXECUTABLE=${EXEC_DIR}/forum_archive_server.py

LOG_DIR=${CURR_SCRIPTS_DIR}/../logs
if [[ ! -d ${LOG_DIR} ]]
then
    mkdir -p ${LOG_DIR}
fi
LOG_FILE=$(echo ${LOG_DIR}/forum_archive_server_`date`.log | sed 's/[ ]/_/g')
echo "FAQ entry requests: keywords,question_id,session_id,rank,uid" > $LOG_FILE
echo "Feedback: feedack,session_id,rank,uid" >> $LOG_FILE

# Need to be in the proper Anaconda environment,
# otherwise Python load paths won't be properly set:
# logInfo "Activating Anaconda data_intake environment..."

cd $CURR_SCRIPTS_DIR
source ${HOME}/anaconda2/bin/activate forum_archive_server

cd ${EXEC_DIR}
#********
#echo "Log file: '${LOG_FILE}'"
#********
nohup ./forum_archive_server.py  >> ${LOG_FILE} 2>&1 &



