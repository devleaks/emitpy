from flask import Flask, render_template, request, flash, Markup, redirect, url_for, jsonify
from flask_wtf import FlaskForm, CSRFProtect
from wtforms.fields import *
from wtforms import validators
from flask_bootstrap import Bootstrap5, SwitchField
from datetime import datetime, timedelta

import json
import logging
import re

import emitpy

from emitpy.emitapp import EmitApp
from emitpy.parameters import MANAGED_AIRPORT
from emitpy.private import SECRET_KEY
from emitpy.constants import EMIT_RATES
from emitpy.utils import Timezone
from emitpy.aircraft import AircraftPerformance as Aircraft
from emitpy.airport import Airport
from emitpy.business import Airline
from emitpy.service import Service, ServiceVehicle, Mission, MissionVehicle
from emitpy.emit import Emit, Format, Queue, RedisUtils

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("app")

app = Flask(__name__)
app.secret_key = SECRET_KEY

# set default button sytle and size, will be overwritten by macro parameters
app.config['BOOTSTRAP_BTN_STYLE'] = 'primary'
app.config['BOOTSTRAP_BTN_SIZE'] = 'sm'
app.config['BOOTSTRAP_BOOTSWATCH_THEME'] = 'lux'  # uncomment this line to test bootswatch theme

bootstrap = Bootstrap5(app)
csrf = CSRFProtect(app)

# git describe --tags
# git log -1 --format=%cd --relative-date
# + redis_connect info
logger.info(f"emitpy {emitpy.__version__} starting..")

e = EmitApp(MANAGED_AIRPORT)
r = RedisUtils()

# # using regex validator instead of this custom one.
# def validate_icao24(form, field):
#     re.compile('[0-9A-F]{6}', re.IGNORECASE)
#     if re.match(field.data) is None:
#         raise ValidationError('Must be a 6-digit hexadecimal number [0-9A-F]{6}')

class CreateFlightForm(FlaskForm):
    airline = SelectField(choices=Airline.getCombo())
    flight_number = StringField(validators=[validators.InputRequired()])
    flight_date = DateField(validators=[validators.optional()])
    flight_time = TimeField(validators=[validators.optional()])
    movement = RadioField(choices=[('arrival', 'Arrival'), ('departure', 'Departure')], validators=[validators.InputRequired("Please provide movement type")])
    airport = SelectField(choices=Airport.getCombo())
    ramp = SelectField(choices=e.airport.getRampCombo())
    aircraft_type = SelectField(choices=Aircraft.getCombo())
    aircraft_reg = StringField("Aircraft Registration", description="Aircraft registration in country of operation (tail number)", validators=[validators.InputRequired("Please provide aircraft registration")])
    call_sign = StringField(description="Aircraft call sign in operation, usually the flight number", validators=[validators.InputRequired("Please provide aircraft callsign")])
    icao24 = StringField(description="ICAO 24 bit transponder address in hexadecimal form",
                         validators=[validators.InputRequired("Please provide aircraft ADS-B transponder address"),
                                     validators.Regexp("[0-9A-F]{6}", flags=re.IGNORECASE, message="Must be a 6-digit hexadecimal number [0-9A-F]{6}")])
    runway = SelectField(choices=e.airport.getRunwayCombo())
    emit_rate = SelectField(choices=EMIT_RATES, default="30",
                            description="Rate, in seconds, at which position will be emitted",
                            validators=[validators.InputRequired("Please provide movement type")])
    queue = SelectField(choices=Queue.getCombo())
    # DANGEROUS
    create_services = BooleanField("Create flight services", description="Note: Services created depends on airline, aircraft type, ramp.")
    submit = SubmitField("Create flight")

    @classmethod
    # https://stackoverflow.com/questions/12170995/flask-and-wtforms-how-to-get-wtforms-to-refresh-select-data
    def new(cls):
        # Instantiate the form
        form = cls()

        # Update the choices for the agency field
        form.airline.data = "QR"
        form.queue.choices = Queue.getCombo()
        return form

@app.route('/create_flight', methods=['GET', 'POST'])
def create_flight_form():
    form = CreateFlightForm.new()
    if form.validate_on_submit():
        input_d = form.flight_date.data if form.flight_date.data is not None else datetime.now()
        input_t = form.flight_time.data if form.flight_time.data is not None else datetime.now()
        dt = datetime(year=input_d.year,
                      month=input_d.month,
                      day=input_d.day,
                      hour=input_t.hour,
                      minute=input_t.minute)
        ret = e.do_flight(queue=form.queue.data,
                          emit_rate=int(form.emit_rate.data),
                          airline=form.airline.data,
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
        if ret.status == 0:
            flash('Flight created', 'success')
        else:
            flash(ret.message, 'error')
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
    quantity = FloatField(validators=[validators.InputRequired("Please provide a quantity to serve")])
    service_vehicle_type = SelectField(choices=ServiceVehicle.getCombo())
    service_vehicle_reg = StringField("Vehicle Registration", description="Vehicle registration", validators=[validators.InputRequired("Please provide aircraft registration")])
    icao24 = StringField(description="ICAO 24 bit transponder address in hexadecimal form",
                         validators=[validators.InputRequired("Please provide aircraft ADS-B transponder address"),
                                     validators.Regexp("[0-9A-F]{6}", flags=re.IGNORECASE, message="Must be a 6-digit hexadecimal number [0-9A-F]{6}")])
    service_pos = [('depot', 'Depot'), ('rest-area', 'Rest Area')] + e.airport.getRampCombo() + e.airport.getServicePoisCombo()
    previous_position = SelectField(choices=service_pos, description="Position where the service vehicle is coming from")
    next_position = SelectField(choices=service_pos, description="Position where the service vehicle is going to after service")
    service_date = DateField(validators=[validators.optional()])
    service_time = TimeField(validators=[validators.optional()])
    emit_rate = SelectField(choices=EMIT_RATES, default="30",
                            description="Rate, in seconds, at which position will be emitted",
                            validators=[validators.InputRequired("Please provide movement type")])
    queue = SelectField(choices=Queue.getCombo())
    submit = SubmitField("Create service")

@app.route('/create_service', methods=['GET', 'POST'])
def create_service_form():
    form = CreateServiceForm()
    if form.validate_on_submit():
        input_d = form.service_date.data if form.service_date.data is not None else datetime.now()
        input_t = form.service_time.data if form.service_time.data is not None else datetime.now()
        dt = datetime(year=input_d.year,
                      month=input_d.month,
                      day=input_d.day,
                      hour=input_t.hour,
                      minute=input_t.minute)
        ret = e.do_service(queue=form.queue.data,
                           emit_rate=int(form.emit_rate.data),
                           operator=form.handler.data,
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
        if ret.status == 0:
            flash('Service created', 'success')
        else:
            flash(ret.message, 'error')
        return redirect(url_for('index'))
    return render_template(
        'create.html',
        title="Create service",
        create_form=form
    )


class CreateMissionForm(FlaskForm):
    operator = SelectField(choices=[('QAS', 'Qatar Airport Security'), ('QAFD', 'Qatar Airport Fire Department'), ('QAPD', 'Qatar Airport Police Department')])
    mission = SelectField(choices=Mission.getCombo())
    service_vehicle_type = SelectField(choices=MissionVehicle.getCombo())
    service_vehicle_reg = StringField("Vehicle Registration", description="Vehicle registration or identifier", validators=[validators.InputRequired("Please provide vehicle registration")])
    icao24 = StringField(description="ICAO 24 bit transponder address in hexadecimal form",
                         validators=[validators.InputRequired("Please provide aircraft ADS-B transponder address"),
                                     validators.Regexp("[0-9A-F]{6}", flags=re.IGNORECASE, message="Must be a 6-digit hexadecimal number [0-9A-F]{6}")])
    previous_position = SelectField(choices=e.airport.getPOICombo(), description="Position where the mission vehicle will start")
    next_position = SelectField(choices=e.airport.getPOICombo(), description="Position where the mission vehicle will go after last checkpoint")
    mission_date = DateField(validators=[validators.optional()])
    mission_time = TimeField(validators=[validators.optional()])
    emit_rate = SelectField(choices=EMIT_RATES, default="30",
                            description="Rate, in seconds, at which position will be emitted",
                            validators=[validators.InputRequired("Please provide movement type")])
    queue = SelectField(choices=Queue.getCombo())
    submit = SubmitField("Create service")

@app.route('/create_mission', methods=['GET', 'POST'])
def create_mission_form():
    form = CreateMissionForm()
    if form.validate_on_submit():
        input_d = form.mission_date.data if form.mission_date.data is not None else datetime.now()
        input_t = form.mission_time.data if form.mission_time.data is not None else datetime.now()
        dt = datetime(year=input_d.year,
                      month=input_d.month,
                      day=input_d.day,
                      hour=input_t.hour,
                      minute=input_t.minute)
        ret = e.do_mission(queue=form.queue.data,
                           emit_rate=int(form.emit_rate.data),
                           operator=form.operator.data,
                           checkpoints=[],
                           mission=form.mission.data,
                           vehicle_model=form.service_vehicle_type.data,
                           vehicle_ident=form.service_vehicle_reg.data,
                           vehicle_icao24=form.icao24.data,
                           vehicle_startpos=form.previous_position.data,
                           vehicle_endpos=form.next_position.data,
                           scheduled=dt.isoformat())
        if ret.status == 0:
            flash('Mission created', 'success')
        else:
            flash(ret.message, 'error')
        return redirect(url_for('index'))
    return render_template(
        'create.html',
        title="Create mission",
        create_form=form
    )


class RescheduleForm(FlaskForm):
    movement = SelectField(choices=r.list_emits(), description="Movement to synchronize", id="movement_id")
    syncname = SelectField(choices=[], description="Synchronization event", id="syncname_id", validate_choice=False)  # Emit.getCombo()
    new_date = DateField(description="Date of synchronized event", validators=[validators.optional()])
    new_time = TimeField(description="Time of synchronized event", validators=[validators.optional()])
    queue = SelectField(choices=Queue.getCombo())
    submit = SubmitField("New ETA")

    @classmethod
    # https://stackoverflow.com/questions/12170995/flask-and-wtforms-how-to-get-wtforms-to-refresh-select-data
    def new(cls):
        form = cls()
        form.movement.choices = r.list_emits()
        return form

@app.route('/schedule', methods=['GET', 'POST'])
def create_schedule_form():
    form = RescheduleForm.new()
    if form.validate_on_submit():
        input_d = form.new_date.data if form.new_date.data is not None else datetime.now()
        input_t = form.new_time.data if form.new_time.data is not None else datetime.now()
        dt = datetime(year=input_d.year,
                      month=input_d.month,
                      day=input_d.day,
                      hour=input_t.hour,
                      minute=input_t.minute)
        ret = e.do_schedule(queue=form.queue.data, ident=form.movement.data, sync=form.syncname.data, scheduled=dt.isoformat())
        if ret.status == 0:
            flash(f'Re-scheduled {form.movement.data}', 'success')
        else:
            flash(ret.message, 'error')
        return redirect(url_for('index'))
    return render_template(
        'create-syncs.html',
        title="Reschedule movement",
        create_form=form
    )

# Helper for cascaded combo
@app.route('/emitsyncs/<emitid>')
def emitsyncs(emitid):
    l = r.getSyncsForEmit(emit_id=emitid)
    return jsonify(syncs=l)


class RemoveForm(FlaskForm):
    movement = SelectField(choices=r.list_emits())
    queue = SelectField(choices=Queue.getCombo())
    submit = SubmitField("Remove movement from queue")

    @classmethod
    def new(cls):
        form = cls()
        form.movement.choices = r.list_emits()
        return form

@app.route('/remove', methods=['GET', 'POST'])
def create_remove_form():
    form = RemoveForm.new()
    if form.validate_on_submit():
        ret = e.do_delete(queue=form.queue.data, ident=form.movement.data)
        if ret.status == 0:
            flash(f'Removed {form.movement.data}', 'success')
        else:
            flash(ret.message, 'error')
        return redirect(url_for('index'))
    return render_template(
        'create.html',
        title="Remove movement",
        create_form=form
    )


class CreateQueueForm(FlaskForm):
    queue_name = StringField("Queue name", description="Name of queue")
    formatting = SelectField(choices=Format.getCombo(), description="Data formatter for the GeoJSON Feature<Point>")
    simulation_date = DateField(description="Start date of queue", validators=[validators.optional()])
    simulation_time = TimeField(description="Start time of queue", validators=[validators.optional()])
#    speed = DecimalRangeField()
    speed = FloatField(default=1, description="1 = real time speed, smaller than 1 slows down, larger than 1 speeds up. Ex: speed=60 one minute last one second.")
    submit = SubmitField("Create queue")

@app.route('/create_queue', methods=['GET', 'POST'])
def create_queue_form():
    form = CreateQueueForm()
    if form.validate_on_submit():
        if form.simulation_date.data is not None or form.simulation_time.data is not None:
            input_d = form.simulation_date.data if form.simulation_date.data is not None else datetime.now()
            input_t = form.simulation_time.data if form.simulation_time.data is not None else datetime.now()
            dt = datetime(year=input_d.year,
                          month=input_d.month,
                          day=input_d.day,
                          hour=input_t.hour,
                          minute=input_t.minute).isoformat()
        else:
            dt = None
        ret = e.do_create_queue(name=form.queue_name.data,
                                formatting=form.formatting.data,
                                starttime=dt,
                                speed=float(form.speed.data)
        )
        if ret.status == 0:
            flash(f'Queue {form.queue_name.data} created', 'success')
        else:
            flash(ret.message, 'error')
        return redirect(url_for('index'))
    return render_template(
        'create.html',
        title="Manage output queues",
        create_form=form
    )


class ResetQueueForm(FlaskForm):
    queue_name = SelectField(choices=Queue.getCombo())
    simulation_date = DateField(description="Start date of queue", validators=[validators.optional()])
    simulation_time = TimeField(description="Start time of queue", validators=[validators.optional()])
#    speed = DecimalRangeField()
    speed = FloatField(default=1, description="1 = real time speed, smaller than 1 slows down, larger than 1 speeds up. Ex: speed=60 one minute last one second.")
    submit = SubmitField("Reset queue")
    @classmethod
    def new(cls):
        form = cls()
        form.queue_name.choices = Queue.getCombo()
        return form

@app.route('/reset_queue', methods=['GET', 'POST'])
def reset_queue_form():
    form = ResetQueueForm.new()
    if form.validate_on_submit():
        if form.simulation_date.data is not None or form.simulation_time.data is not None:
            input_d = form.simulation_date.data if form.simulation_date.data is not None else datetime.now()
            input_t = form.simulation_time.data if form.simulation_time.data is not None else datetime.now()
            dt = datetime(year=input_d.year,
                          month=input_d.month,
                          day=input_d.day,
                          hour=input_t.hour,
                          minute=input_t.minute).isoformat()
        else:
            dt = None
        ret = e.do_reset_queue(name=form.queue_name.data,
                               starttime=dt,
                               speed=float(form.speed.data)
        )
        if ret.status == 0:
            flash(f'Queue {form.queue_name.data} reset', 'success')
        else:
            flash(ret.message, 'error')
        return redirect(url_for('index'))
    return render_template(
        'create.html',
        title="Manage output queues",
        create_form=form
    )


class DeleteQueueForm(FlaskForm):
    queue_name = SelectField(choices=Queue.getCombo())
    submit = SubmitField("Delete queue")
    @classmethod
    def new(cls):
        form = cls()
        form.queue_name.choices = Queue.getCombo()
        return form

@app.route('/delete_queue', methods=['GET', 'POST'])
def delete_queue_form():
    form = DeleteQueueForm.new()
    if form.validate_on_submit():
        ret = e.do_delete_queue(name=form.queue_name.data)
        if ret.status == 0:
            flash(f'Queue {form.queue_name.data} deleted', 'success')
        else:
            flash(ret.message, 'error')
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
