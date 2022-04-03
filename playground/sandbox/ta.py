from ..src.emitpy.task import Project, Task, RelatedTask



def rotation():
    rotation = Project()

    marsharr = Task("marshaling arrival")
    chockson = Task("chocks on", 1, marsharr)
    apuon = Task("apu connected", 0, marsharr)

    project.add(marsharr)

    cargo = Task("cargo")
    cargodooropen = Task("cargo door open", 0, cargo)
    cargounloading = Task("cargo unloading", 20, cargo)
    cargoloading = Task("cargo loading", 25, cargo)
    cargodoorclosed = Task("cargo door closed", 0, cargo)

    baggage = Task("baggage")
    baggagedooropen = Task("baggage door open", 0, cargo)
    baggageunloading = Task("baggage unloading", 20, cargo)
    baggageloading = Task("baggage loading", 25, cargo)
    baggagedoorclosed = Task("baggage door closed", 0, cargo)

    pax = Task("pax")
    paxdooropen = Task("pax door open", 0, pax)
    paxdeboarding = Task("deboarkding", 20, pax)
    paxboarding = Task("boarding", 25, pax)
    paxdoorclosed = Task("pax door closed", 0, pax)

    refueling = Task("refueling", 25)
    refueling.after(paxdeboarding, "SE", 2)
    paxboarding.after(refueling, "SE", 2)

    cateringoff = Task("catering offloading", 10)
    cateringoff.after(paxdeboarding, "SE", -5)  # 5 min before last pax exists

    cleaning = Task("cleaning", 25)
    cleaning.after(paxdeboarding, "SE", -5)  # 5 min before last pax exists

    cateringon = Task("catering loading", 15)
    cateringon.after(cateringoff, "SE", 0)

    sewage = Task("sewage", 15)
    sewage.after(cargodooropen, "SE", 2)

    water = Task("water", 15)
    water.after(sewage, "SE", 5)

    marshdept = Task("marshaling departure")
    apuoff = Task("apu disconnected", 0, marshdept)
    chocksoff = Task("chocks off", 1, marshdept)
    chocksoff.after(apuoff, "SE", 1)
    pushback = Task("push back", 5, marshdept)
    pushback.after(chocksoff, "SE", 1)

