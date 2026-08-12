import enum


class PaymentMethod(str, enum.Enum):
    BITCOIN = "Bitcoin"
    CREDIT_CARD = "newcc"
    PAYPAL = "paypal"
