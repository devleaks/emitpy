# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, flash, Markup, redirect, url_for, jsonify
from flask_wtf import FlaskForm, CSRFProtect
from wtforms.fields import *
from flask_bootstrap import Bootstrap5, SwitchField
from datetime import datetime, timedelta

import json
import logging

from entity.emitapp import EmitApp
from entity.parameters import MANAGED_AIRPORT
from entity.utils import Timezone
from entity.aircraft import AircraftPerformance as Aircraft
from entity.airport import Airport
from entity.business import Airline
from entity.service import Service, ServiceVehicle
from entity.emit import Emit, Format
from entity.utils import RedisUtils

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("app")

app = Flask(__name__)
app.secret_key = 'dev'

# set default button sytle and size, will be overwritten by macro parameters
app.config['BOOTSTRAP_BTN_STYLE'] = 'primary'
app.config['BOOTSTRAP_BTN_SIZE'] = 'sm'
app.config['BOOTSTRAP_BOOTSWATCH_THEME'] = 'lux'  # uncomment this line to test bootswatch theme

bootstrap = Bootstrap5(app)
csrf = CSRFProtect(app)


e = EmitApp(MANAGED_AIRPORT)
r = RedisUtils()


class CreateFlightForm(FlaskForm):
    airline = SelectField(choices=Airline.getCombo())
    flight_number = StringField()
    flight_date = DateField()
    flight_time = TimeField()
    movement = RadioField(choices=[('arrival', 'Arrival'), ('departure', 'Departure')])
    airport = SelectField(choices=Airport.getCombo())
    ramp = SelectField(choices=e.airport.getRampCombo())
    aircraft_type = SelectField(choices=Aircraft.getCombo())
    aircraft_reg = StringField("Aircraft Registration", description="Aircraft registration in country of operation (tail number)")
    call_sign = StringField(description="Aircraft call sign in operation, usually the flight number")
    icao24 = StringField(description="ICAO 24 bit transponder address in hexadecimal form")
    runway = SelectField(choices=e.airport.getRunwayCombo())
    # DANGEROUS
    create_services = BooleanField("Create flight services", description="Note: Services created depends on airline, aircraft type, ramp.")
    submit = SubmitField("Create flight")

@app.route('/create_flight', methods=['GET', 'POST'])
def create_flight_form():
    form = CreateFlightForm()
    if form.validate_on_submit():
        dt = form.flight_date.data + timedelta(hours=form.flight_time.data.hour, minutes=form.flight_time.data.minute)
        ret = e.do_flight(airline=form.airline.data,
                    flightnumber=form.flight_number.data,
                    scheduled=dt.isoformat(),
                    apt=form.airport.data,
                    movetype=form.movement.data,
                    acarr=(form.aircraft_type.data, form.aircraft_type.data),
                    ramp=form.ramp.data,
                    icao24=form.icao24.data,
                    acreg=form.aircraft_reg.data,
                    runway=form.runway.data,
                    do_services=form.create_services.data)
        if ret.errno == 0:
            flash('Flight created', 'success')
        else:
            flash(ret.errmsg, 'error')
        return redirect(url_for('index'))
    return render_template(
        'create.html',
        title="Create flight",
        create_form=form
    )


class CreateServiceForm(FlaskForm):
    ramp = SelectField(choices=e.airport.getRampCombo())
    aircraft_type = SelectField(choices=Aircraft.getCombo())
    handler = SelectField(choices=[('QAS', 'Qatar Airport Services'), ('BRU', 'Bru Partners'), ('SWI', 'Swissport')])
    service = SelectField(choices=Service.getCombo())
    quantity = FloatField()
    service_vehicle_type = SelectField(choices=ServiceVehicle.getCombo())
    service_vehicle_reg = StringField("Vehicle Registration", description="Vehicle registration or identifier")
    icao24 = StringField(description="ICAO 24 bit transponder address in hexadecimal form of service vehicle")
    service_pos = [('depot', 'Depot'), ('rest-area', 'Rest Area')] + e.airport.getRampCombo() + e.airport.getServicePoisCombo()
    previous_position = SelectField(choices=service_pos, description="Position where the service vehicle is coming from")
    next_position = SelectField(choices=service_pos, description="Position where the service vehicle is going to after service")
    service_date = DateField()
    service_time = TimeField()
    submit = SubmitField("Create service")

@app.route('/create_service', methods=['GET', 'POST'])
def create_service_form():
    form = CreateServiceForm()
    if form.validate_on_submit():
        dt = form.service_date.data + timedelta(hours=form.service_time.data.hour, minutes=form.service_time.data.minute)
        ret = e.do_service(operator=form.handler.data,
                     service=form.service.data,
                     quantity=form.quantity.data,
                     ramp=form.ramp.data,
                     aircraft=form.aircraft_type.data,
                     vehicle_model=form.service_vehicle_type.data,
                     vehicle_ident=form.service_vehicle_reg.data,
                     vehicle_icao24=form.icao24.data,
                     vehicle_startpos=form.previous_position.data,
                     vehicle_endpos=form.next_position.data,
                     scheduled=dt.isoformat())
        if ret.errno == 0:
            flash('Service created', 'success')
        else:
            flash(ret.errmsg, 'error')
        return redirect(url_for('index'))
    return render_template(
        'create.html',
        title="Create service",
        create_form=form
    )


class RescheduleForm(FlaskForm):
    movement = SelectField(choices=r.list_emits(), id="movement_id")
    syncname = SelectField(choices=[], id="syncname_id", validate_choice=False)  # Emit.getCombo()
    new_date = DateField()
    new_time = TimeField()
    submit = SubmitField("New ETA")

    @classmethod
    # https://stackoverflow.com/questions/12170995/flask-and-wtforms-how-to-get-wtforms-to-refresh-select-data
    def new(cls):
        # Instantiate the form
        form = cls()

        # Update the choices for the agency field
        form.movement.choices = r.list_emits()
        return form

@app.route('/schedule', methods=['GET', 'POST'])
def create_schedule_form():
    form = RescheduleForm.new()
    if form.validate_on_submit():
        dt = form.new_date.data + timedelta(hours=form.new_time.data.hour, minutes=form.new_time.data.minute)
        ret = e.do_schedule(ident=form.movement.data, sync=form.syncname.data, scheduled=dt.isoformat())
        if ret.errno == 0:
            flash(f'Re-scheduled {form.movement.data}', 'success')
        else:
            flash(ret.errmsg, 'error')
        return redirect(url_for('index'))
    return render_template(
        'create-alt.html',
        title="Reschedule movement",
        create_form=form
    )


@app.route('/emitsyncs/<emitid>')
def emitsyncs(emitid):
    l = r.getSyncsForEmit(emit_id=emitid)
    return jsonify(syncs=l)


class RemoveForm(FlaskForm):
    movement = SelectField(choices=r.list_emits())
    submit = SubmitField("Remove movement from queue")

    @classmethod
    # https://stackoverflow.com/questions/12170995/flask-and-wtforms-how-to-get-wtforms-to-refresh-select-data
    def new(cls):
        # Instantiate the form
        form = cls()

        # Update the choices for the agency field
        form.movement.choices = r.list_emits()
        return form

@app.route('/remove', methods=['GET', 'POST'])
def create_remove_form():
    form = RemoveForm.new()
    if form.validate_on_submit():
        ret = e.do_delete(ident=form.movement.data)
        if ret.errno == 0:
            flash(f'Removed {form.movement.data}', 'success')
        else:
            flash(ret.errmsg, 'error')
        return redirect(url_for('index'))
    return render_template(
        'create.html',
        title="Remove movement",
        create_form=form
    )


class QueueForm(FlaskForm):
    queue_name = StringField("Queue name")
    formatting = SelectField(choices=Format.getCombo())
    simulation_date = DateField()
    simulation_time = TimeField()
    speed = DecimalRangeField()
    submit = SubmitField("Create queue")

@app.route('/queue', methods=['GET', 'POST'])
def create_queue_form():
    form = QueueForm()
    if form.validate_on_submit():
        dt = form.simulation_date.data + timedelta(hours=form.simulation_time.data.hour, minutes=form.simulation_time.data.minute)
        ret = e.do_queue(name=form.queue_name.data,
                         formatting=form.formatting.data,
                         starttime=dt.isoformat(),
                         speed=float(form.speed.data)
        )
        if ret.errno == 0:
            flash(f'Queue {form.queue_name.data} created', 'success')
        else:
            flash(ret.errmsg, 'error')
        return redirect(url_for('index'))
    return render_template(
        'create.html',
        title="Manage output queues",
        create_form=form
    )


@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    app.run(debug=True)
