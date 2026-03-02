from datetime import date, timedelta


def predict_next_service(
    service_type: str,
    current_mileage: int | None,
):
    service_type = (service_type or "").lower()

    if "oil" in service_type:
        months = 6
        mileage_interval = 5000
    elif "major" in service_type:
        months = 12
        mileage_interval = 10000
    else:
        months = 6
        mileage_interval = 7000

    next_date = date.today() + timedelta(days=30 * months)

    next_mileage = None
    if current_mileage:
        next_mileage = current_mileage + mileage_interval

    return next_date, next_mileage
