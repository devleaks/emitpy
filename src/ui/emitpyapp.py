# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, flash, Markup, redirect, url_for
from flask_wtf import FlaskForm, CSRFProtect
from wtforms.fields import *
from flask_bootstrap import Bootstrap5, SwitchField

app = Flask(__name__)
app.secret_key = 'dev'

# set default button sytle and size, will be overwritten by macro parameters
app.config['BOOTSTRAP_BTN_STYLE'] = 'primary'
app.config['BOOTSTRAP_BTN_SIZE'] = 'sm'
app.config['BOOTSTRAP_BOOTSWATCH_THEME'] = 'lux'  # uncomment this line to test bootswatch theme

bootstrap = Bootstrap5(app)
csrf = CSRFProtect(app)


class CreateFlightForm(FlaskForm):
    airline = SelectField(choices=[('QR', 'Qatar Airways'), ('KV', 'Air Belgium')])
    flight_number = StringField()
    flight_date = DateField()
    flight_time = TimeField()
    movement = RadioField(choices=[('arrival', 'Arrival'), ('departure', 'Departure')])
    airport = SelectField(choices=[('BRU', 'Brussels, Belgium'), ('DBX', 'Dubaï, UEM')])
    ramp = SelectField(choices=[('A7', 'A7'), ('C12', 'C12'), ('510', '510')])
    aircraft_type = SelectField(choices=[('A321', 'Airbus A321'), ('B777', 'Boeing 777-800')])
    aircraft_reg = StringField("Aircraft Registration", description="Aircraft registration in country of operation (tail number)")
    call_sign = StringField(description="Aircraft call sign in operation, usually the flight number")
    icao24 = StringField(description="ICAO 24 bit transponder address in hexadecimal form")
    runway = SelectField(choices=[('RW16L', '16 L'), ('RW16R', '16 R'), ('RW34L', '34 L'), ('RW34R', '34 R')])
    create_services = BooleanField("Create flight services", description="(Note: Depends on airline, aircraft type, ramp.)")
    submit = SubmitField("Create flight")

@app.route('/create_flight', methods=['GET', 'POST'])
def create_flight_form():
    form = CreateFlightForm()
    if form.validate_on_submit():
        flash('Flight created')
        return redirect(url_for('index'))
    return render_template(
        'create.html',
        title="Create flight",
        create_form=form
    )


class CreateServiceForm(FlaskForm):
    flight_number = StringField()
    flight_date = DateField()
    flight_time = TimeField()
    ramp = SelectField(choices=[('A7', 'A7'), ('C12', 'C12'), ('510', '510')])
    aircraft_type = SelectField(choices=[('A321', 'Airbus A321'), ('B777', 'Boeing 777-800')])
    handler = SelectField(choices=[('QAS', 'Qatar Airport Services'), ('BRU', 'Bru Partners')])
    service = SelectField(choices=[('fuel', 'Fuel'), ('catering', 'Catering')])
    quantity = FloatField()
    service_vehicle = SelectField(choices=[('jet', 'Pump'), ('turboprop', 'Large'), ('prop', 'Medium')])
    icao24 = StringField(description="ICAO 24 bit transponder address in hexadecimal form of service vehicle")
    previous_position = SelectField(choices=[('depot', 'Depot'), ('rest-area', 'Rest Area'), ('C12', 'C12')])
    next_position = SelectField(choices=[('depot', 'Depot'), ('rest-area', 'Rest Area'), ('C12', 'C12')])
    submit = SubmitField("Create service")

@app.route('/create_service', methods=['GET', 'POST'])
def create_service_form():
    form = CreateServiceForm()
    if form.validate_on_submit():
        flash('Service created')
        return redirect(url_for('index'))
    return render_template(
        'create.html',
        title="Create service",
        create_form=form
    )


class RescheduleForm(FlaskForm):
    movement = SelectField(choices=[('F-QR0195-BRU-20220322', 'Flight QR 195 BRU-DOH 17:15'), ('S-C12-FUE-20220322-1730', 'Ramp C12, Fuel service QR 195')])
    new_date = DateField()
    new_time = TimeField()
    submit = SubmitField("New ETA")

@app.route('/schedule', methods=['GET', 'POST'])
def create_schedule_form():
    form = RescheduleForm()
    if form.validate_on_submit():
        flash('Re-scheduled')
        return redirect(url_for('index'))
    return render_template(
        'create.html',
        title="Reschedule movement",
        create_form=form
    )


class RemoveForm(FlaskForm):
    movement = SelectField(choices=[('F-QR0195-BRU-20220322', 'Flight QR 195 BRU-DOH 17:15'), ('S-C12-FUE-20220322-1730', 'Ramp C12, Fuel service QR 195')])
    submit = SubmitField("Remove movement")

@app.route('/remove', methods=['GET', 'POST'])
def create_remove_form():
    form = RemoveForm()
    if form.validate_on_submit():
        flash('Removed')
        return redirect(url_for('index'))
    return render_template(
        'create.html',
        title="Remove movement",
        create_form=form
    )


@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    app.run(debug=True)
