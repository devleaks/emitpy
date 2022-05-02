from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import csv
import os
import json
import random

filename = os.path.join("..", "data", "managedairport", "OTHH", "flights", "2019_W15_ROTATION_RAW.csv")
file = open(filename, "r")
csvdata = csv.DictReader(file)
cal={}
bays = {}
entries = []

for r in csvdata:
    bay = r["BAY_x"]
    if bay not in bays.keys():
        bid = len(bays) + 1
        bays[bay] = {
            "id": bid,
            "name": bay
        }

    eid = len(entries) + 1
    entries.append({
        "id": eid,
        "name": '<div>'+r["AIRLINE CODE_x"]+r["FLIGHT NO_x"]+">"+r["AIRLINE CODE_y"]+r["FLIGHT NO_y"]+'</div>',
        "start": r['FLIGHT SCHEDULED TIME_x'],
        "end": r['FLIGHT SCHEDULED TIME_y'],
        "sectionID": bays[bay]["id"],
        "classes": random.choice(['item-status-none', 'item-status-one', 'item-status-two', 'item-status-three'])
    })

cal["Items"] = entries
cal["Sections"] = list(sorted(bays.values(), key=lambda x: x["name"]))

app = FastAPI()

app.mount("/static", StaticFiles(directory="web/static"), name="static")


templates = Jinja2Templates(directory="web/templates")


@app.get("/")
async def read_item(request: Request):
    return templates.TemplateResponse("alloc.html", {"request": request, "calstr": json.dumps(cal)})

@app.get("/alloc")
async def read_item():
    return JSONResponse(content=cal)
