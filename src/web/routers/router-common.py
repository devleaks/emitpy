

def include_routers(app, emitpyapp):
    app.include_router(flights.router)
    app.include_router(services.router)
    app.include_router(missions.router)
    app.include_router(queues.router)
    app.include_router(airport.router)




def LOV_Validator(
    value: str,
    valid_values: List[str],
    invalid_message: str) -> str:
    if value not in valid_values:
        raise ValueError(invalid_message)
    return value
