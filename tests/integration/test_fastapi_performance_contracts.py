"""Contract tests for FastAPI benchmark instrumentation."""

from benchmarks.workloads.application.inventory import WORKLOADS as APPLICATION_WORKLOADS
from benchmarks.workloads.component.fastapi import WORKLOADS as COMPONENT_WORKLOADS


def test_fastapi_application_inventory_contains_the_null_route_pair() -> None:
    assert tuple(workload.name for workload in APPLICATION_WORKLOADS) == (
        'fastapi_no_injection',
        'fastapi_cpu_light_endpoint',
        'fastapi_request_scoped_graph',
        'fastapi_singletons_and_transients',
        'fastapi_async_resource_teardown',
        'fastapi_endpoint_with_work',
        'fastapi_application_startup',
    )


def test_fastapi_application_pairs_have_equal_observations() -> None:
    for workload in APPLICATION_WORKLOADS:
        if workload.baseline is not None:
            assert workload.subject.observe() == workload.baseline.observe()


def test_fastapi_component_inventory_decomposes_lazy_request_costs() -> None:
    assert tuple(workload.name for workload in COMPONENT_WORKLOADS) == (
        'fastapi_lazy_host_publication',
        'fastapi_lazy_frame_activation_and_drain',
        'fastapi_endpoint_program_one_key',
        'fastapi_endpoint_program_many_keys',
        'fastapi_request_seed_read',
        'fastapi_async_resource_close',
    )


def test_fastapi_component_observations_capture_exact_lifecycle_semantics() -> None:
    observed = {workload.name: workload.subject.observe() for workload in COMPONENT_WORKLOADS}

    assert observed['fastapi_lazy_host_publication'].result == '200 {"value":"plain"}; frames=0; programs=0'
    assert observed['fastapi_lazy_host_publication'].constructed == ()
    assert observed['fastapi_lazy_host_publication'].closed == ()
    assert observed['fastapi_lazy_frame_activation_and_drain'].result == '200 {"value":"scoped"}; frames=1; programs=1'
    assert observed['fastapi_lazy_frame_activation_and_drain'].constructed == ('ScopedValue',)
    assert observed['fastapi_lazy_frame_activation_and_drain'].closed == ()
    assert observed['fastapi_endpoint_program_one_key'].result == '200 {"value":"singleton"}; frames=0; programs=1'
    assert observed['fastapi_endpoint_program_one_key'].constructed == ()
    assert (
        observed['fastapi_endpoint_program_many_keys'].result
        == '200 {"left":"one","right":"two"}; frames=0; programs=1'
    )
    assert observed['fastapi_endpoint_program_many_keys'].constructed == ()
    assert observed['fastapi_request_seed_read'].result == '200 {"path":"/seed"}; frames=1; programs=1'
    assert observed['fastapi_request_seed_read'].constructed == ('RequestSeed',)
    assert observed['fastapi_async_resource_close'].result == '200 {"value":"resource"}; frames=1; programs=1'
    assert observed['fastapi_async_resource_close'].constructed == ('AsyncResource',)
    assert observed['fastapi_async_resource_close'].closed == ('AsyncResource',)
