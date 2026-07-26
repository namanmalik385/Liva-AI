_patient_data_by_user = {}


def get_patient_data(user_id):
    return _patient_data_by_user.setdefault(int(user_id), {})


def clear_patient_data(user_id):
    _patient_data_by_user.pop(int(user_id), None)
