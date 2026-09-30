from fastapi import APIRouter
from gate_lib.api.v2 import build_balance_method
from gate_lib.api.v2 import build_p2p_selector_sale_method
from gate_lib.api.v2 import build_ping_method
from gate_lib.api.v2 import build_refund_method
from gate_lib.api.v2 import build_refund_status_method
from gate_lib.api.v2 import build_sale_confirm_method
from gate_lib.api.v2 import build_sale_method
from gate_lib.api.v2 import build_status_method
from gate_lib.api.v2 import build_terminal_data_schema_method
from gate_lib.api.v2 import build_withdrawal_method
from gate_lib.api.v2 import build_withdrawal_status_method
from api.deps import gate_nambaone


router = APIRouter(tags=["v2"])


build_balance_method(router, gate_nambaone)
build_p2p_selector_sale_method(router, gate_nambaone)
build_ping_method(router, gate_nambaone)
build_refund_method(router, gate_nambaone)
build_refund_status_method(router, gate_nambaone)
build_sale_confirm_method(router, gate_nambaone)
build_sale_method(router, gate_nambaone)
build_status_method(router, gate_nambaone)
build_terminal_data_schema_method(router, gate_nambaone)
build_withdrawal_method(router, gate_nambaone)
build_withdrawal_status_method(router, gate_nambaone)
