import uvicorn

from aura_core.application.api import create_api
from aura_core.config.kernel import KernelConfig
from aura_core.kernel.runtime import AuraKernel


def main() -> None:
    kernel_config = KernelConfig.from_environment()
    kernel = AuraKernel(kernel_config)
    kernel.bootstrap()
    kernel.start()

    app = create_api(
        kernel_config.runtime,
        backend_config=kernel_config.backend,
    )

    try:
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=8000,
        )
    finally:
        kernel.stop()


if __name__ == "__main__":
    main()
