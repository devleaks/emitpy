
from flask import Flask
from flask import json
from flask import request
from random import getrandbits

from entity.utils import FlightRequest, ServiceRequest, EmitRequest, StartQueueRequest, StopQueueRequest


app = Flask(__name__)

generic_flask_post_error = json.dumps({
                "errno": 42,
                "errmsg": "flash request error",
                "data": ""
            })

@app.route("/")
def hello():
    return json.dumps({
            "errno": 0,
            "errmsg": "You're not supposed to come here. But since you came, here is an handy random 24-bit hexadecimal number",
            "data": f"{getrandbits(24):x}"
        })


@app.route('/flight/create', methods=['POST'])
def flight_create():
    if request.method=='POST':
        ident=request.form['airline']
        sname=request.form['flight']
        sdate=request.form['scheduled']
        ident=request.form['apt_from']
        sname=request.form['apt_to']
        sdate=request.form['ramp']
        ident=request.form['icao24']
        sname=request.form['actype']
        sdate=request.form['acreg']
        ident=request.form['runway']
        r = FlightRequest(airline=airline, flight=flight, scheduled=scheduled, apt_from=apt_from, apt_to=apt_to,
                          actype=actype, ramp=ramp, icao24=icao24, acreg=acreg, runway=runway)
        ret = r.run()
        return json.dumps(ret)
    else:
        return generic_flask_post_error


@app.route('/service/create', methods=['POST'])
def service_create():
    if request.method=='POST':
        ident=request.form['operator']
        sname=request.form['flight']
        sdate=request.form['scheduled']
        sname=request.form['service']
        sdate=request.form['ramp']
        ident=request.form['icao24']
        sname=request.form['model']
        sdate=request.form['startpos']
        ident=request.form['endpos']
        r = ServiceRequest(operator=operator, flight=flight, scheduled=scheduled, service=service,
                           ramp=ramp, icao24=icao24, model=model, startpos=startpos, endpos=endpos)
        ret = r.run()
        return json.dumps(ret)
    else:
        return generic_flask_post_error


@app.route('/emit/sync', methods=['POST'])
def emit_sync():
    if request.method=='POST':
        ident=request.form['ident']
        sname=request.form['sync_name']
        sdate=request.form['sync_time']
        r = EmitRequest(ident=ident, sync_name=sname, sync_time=sdate)
        ret = r.run()
        return json.dumps(ret)
    else:
        return generic_flask_post_error


@app.route('/simulation/start', methods=['POST'])
def simulation_start():
    if request.method=='POST':
        ident=request.form['name']
        sname=request.form['sync_time']
        sdate=request.form['speed']
        r = StartQueueRequest(name=name, sync_time=sdate, speed=float(speed))
        ret = r.run()
        return json.dumps(ret)
    else:
        return generic_flask_post_error


@app.route('/simulation/stop', methods=['POST'])
def simulation_stop():
    if request.method=='POST':
        ident=request.form['name']
        r = StopQueueRequest(name=name)
        ret = r.run()
        return json.dumps(ret)
    else:
        return generic_flask_post_error


if __name__ == "__main__":
    #app.run()
    app.run(debug=True)
