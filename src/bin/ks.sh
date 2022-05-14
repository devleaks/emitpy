kill -9 `ps |grep "/Users/pierre/opt/miniconda3/bin/python"|grep -v grep | awk '{print $1}'`
