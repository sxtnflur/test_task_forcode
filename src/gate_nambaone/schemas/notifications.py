from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic.alias_generators import to_camel


class WebhookData(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    guid: str
    status: str | None = None
    # Вебхук о платеже: externalId платежной ссылки, то есть id счета
    external_id: str | None = None
    # Вебхук о возврате: externalGuid возврата, то есть id возврата
    external_guid: str | None = None


class InvoiceNotification(BaseModel):
    """
    Вебхук NambaOne: "Payment Order Updated" или "Refund Order Updated".

    Вебхуки не подписаны, поэтому их содержимому не доверяем: гейт берет из него только id
    и запрашивает актуальный статус через API NambaOne.
    """

    model_config = ConfigDict(extra="ignore")

    type: str
    data: WebhookData


class WithdrawalNotification(BaseModel):
    Param: str | dict | float | bool | None
    Amount: str | int | float | None = None
