# emitpy

Flight path and Ground Support Vehicle path generator


Emitpy sofware aims at generate synthetic ADS-B messages as produced by both flying aircrafts or support vehicles
on the ground of the airport.

It is conceived as a box software, only accessible through a REST api, and producing ADS-B messages on a Redis queue.

This repository only contains code, it does not contain any data (which sometimes is private) which is necessary for it to run.

Documentation [is added as the software evolves](https://devleaks.github.io/emitpy-docs/).

The generator software is written in Python.

The basic stream processor is written in JavaScript with node-red.

The basic viewer software is also written in JavaScript with node-red.

Emitpy sofware is a perpetual beta software.

Major releases are named after naval disasters.
(The name of the disaster is often the name of the ship that sunk.)


`data` folder contains static data for the application, including test data.

`db` folder contains caches, dynamic data (like weather), and outputs from the application.
This latest folder can safely be erased, it is recreated is non existant on starup.

`src` contains the whole application

Documentation is in another repository [emitpy-docs](https://github.com/devleaks/emitpy-docs).