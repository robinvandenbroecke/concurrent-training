"""Evidence-bounded calculation engine that the web/Android client really uses.

Everything in this package is a pure function of its input: no database, no
clock, no network. The legacy three-compartment model under ``app.domain`` is
research code and is deliberately NOT imported here (see MODEL_REGISTER.md).
"""
ENGINE_VERSION = "ct-engine-3.2.1"
CONTRACT_VERSION = "1"
