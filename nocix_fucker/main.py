import time

from loguru import logger

import nocix_fucker
from nocix_fucker import Client
from nocix_fucker import config


def print_logo() -> None:
    print(
        "███╗   ██╗ ██████╗  ██████╗██╗██╗  ██╗     ███████╗██╗   ██╗ ██████╗██╗  ██╗███████╗██████╗\n"
        + "████╗  ██║██╔═══██╗██╔════╝██║╚██╗██╔╝     ██╔════╝██║   ██║██╔════╝██║ ██╔╝██╔════╝██╔══██╗\n"
        + "██╔██╗ ██║██║   ██║██║     ██║ ╚███╔╝█████╗█████╗  ██║   ██║██║     █████╔╝ █████╗  ██████╔╝\n"
        + "██║╚██╗██║██║   ██║██║     ██║ ██╔██╗╚════╝██╔══╝  ██║   ██║██║     ██╔═██╗ ██╔══╝  ██╔══██╗\n"
        + "██║ ╚████║╚██████╔╝╚██████╗██║██╔╝ ██╗     ██║     ╚██████╔╝╚██████╗██║  ██╗███████╗██║  ██║\n"
        + "╚═╝  ╚═══╝ ╚═════╝  ╚═════╝╚═╝╚═╝  ╚═╝     ╚═╝      ╚═════╝  ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝\n"
    )


def print_version() -> None:
    logger.info(f"Running version {nocix_fucker.__version__}")


def main() -> None:
    # Software info
    print_logo()
    print_version()

    # Get config
    cfg = config.get_config()
    if not cfg:
        return

    # Ordering
    logger.info("Starting client")
    client = Client(cfg.browser_dsn, cfg.proxy_dsn)
    try:
        with client:
            # Wait stock
            logger.info("Start waiting until stock available")
            client.wait_until_in_stock(cfg.goods_id, cfg.wait_interval)

            logger.info("In stock, start ordering")
            client.open_cart(cfg.goods_id)

            # Select option
            logger.info("Selecting operating system")
            if not client.select_operating_system("Debian"):
                logger.warning("Debian is not available, trying to select Ubuntu")
                if not client.select_operating_system("Ubuntu"):
                    logger.warning(
                        "Ubuntu is not available, fallback to default system"
                    )

            # Check price
            logger.info("Checking whether the total price matching our target price")
            if not client.match_price(cfg.target_price):
                logger.warning(
                    "Total price does not match our target price, stop ordering"
                )
                return
            logger.info("Total price matched our target price")

            # Continue
            client.click_next_step_button()

            # Customer details
            logger.info("Filling customer information")
            client.fill_in_customer_info(
                new=cfg.new_customer,
                email=cfg.email,
                password=cfg.password,
                first_name=cfg.first_name,
                last_name=cfg.last_name,
                company=cfg.company,
                phone=cfg.phone,
                address=cfg.address,
                city=cfg.city,
                state=cfg.state,
                postal_code=cfg.postal_code,
                country_name=cfg.country_name,
            )

            # Continue
            client.click_next_step_button()

            # Payment details
            logger.info("Filling payment information")
            client.fill_in_payment_info(
                payment_method=cfg.payment_method,
                cc_num=cfg.cc_num,
                cc_exp_month=cfg.cc_exp_month,
                cc_exp_year=cfg.cc_exp_year,
                cc_ccv=cfg.cc_ccv,
                first_name=cfg.first_name,
                last_name=cfg.last_name,
                company=cfg.company,
                address=cfg.address,
                city=cfg.city,
                state=cfg.state,
                postal_code=cfg.postal_code,
                country_name=cfg.country_name,
            )

            # Continue
            client.click_next_step_button()

            # Finalize order
            logger.info("Finalizing order")
            time.sleep(2.5)
            client.click_next_step_button()
            time.sleep(2.5)
            submit_error = client.submit_order()
            if submit_error:
                logger.error(f"Failed to submit the order. Reason: {submit_error}")
                return

            logger.info(f"Goods '{cfg.goods_id}' ordered, enjoy")
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt detected, stopping and exiting")


if __name__ == "__main__":
    main()
