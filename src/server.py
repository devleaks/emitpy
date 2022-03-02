
from flask import Flask
from flask import json
from flask import request

from entity.utils import EmitRequest


app = Flask(__name__)

@app.route("/")
def hello():
    return json.dumps({
            "errno": 404,
            "errmsg": "You're not supposed to come here",
            "data": ""
        })

@app.route('/flight/create',methods=['POST'])
def flight_create():
    return json.dumps({
            "errno": 0,
            "errmsg": "no error",
            "data": "no data"
        })


@app.route('/service/create',methods=['POST'])
def service_create():
    return json.dumps({
            "errno": 0,
            "errmsg": "no error",
            "data": "no data"
        })


@app.route('/emit/sync',methods=['POST'])
def emit_sync():
    # id: str, sync_name: str, sync_time: str
    if request.method=='POST':
       ident=request.form['ident']
       sname=request.form['sync_name']
       sdate=request.form['sync_time']
       r = EmitRequest(ident=ident, sync_name=sname, sync_time=sdate)
       ret = r.run()
       return json.dumps(ret)
    else:
        return "error"


@app.route('/simulation/start',methods=['POST'])
def simulation_start():
    return json.dumps({
            "errno": 0,
            "errmsg": "no error",
            "data": "no data"
        })


@app.route('/simulation/stop')
def simulation_stop():
    return json.dumps({
            "errno": 0,
            "errmsg": "no error",
            "data": "no data"
        })


if __name__ == "__main__":
    #app.run()
    app.run(debug=True)
