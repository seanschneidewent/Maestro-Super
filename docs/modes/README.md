# Modes Roadmap (Fast / Med / Deep)

This folder breaks the implementation plan into phase docs so each stage can be reviewed, tracked, and implemented independently.

## Phases

- [Phase 0 - Contracts & Instrumentation](PHASE_0_CONTRACTS_AND_INSTRUMENTATION.md)
- [Phase 0 - Implementation Summary](PHASE_0_IMPLEMENTATION_SUMMARY.md)
- [Phase 1 - Fast Mode (Reflection-First Routing)](PHASE_1_FAST_MODE_REFLECTION_FIRST_ROUTING.md)
- [Phase 2 - Med Mode (Detail-Level From Brain Mode Outputs)](PHASE_2_MED_MODE_DETAIL_LEVEL_NO_VISION.md)
- [Phase 3 - Deep Mode Enhancements (Vision + Verified Facts)](PHASE_3_DEEP_MODE_VISION_ENHANCEMENTS.md)
- [Phase 4 - Evaluation & Rollout](PHASE_4_EVALUATION_AND_ROLLOUT.md)

## Contracts

- [Mode Contracts](MODE_CONTRACTS.md)
- [Eval Dataset Notes](eval/README.md)

## Guiding Principle

- Fast mode should answer "which sheets should I look at?" quickly and reliably.
- Med mode should answer "which details/regions on those sheets matter?" using *precomputed* Brain Mode outputs (no live vision).
- Deep mode should answer "what does it say/measure/show exactly?" using vision + zoom/crop with verifiable outputs.
