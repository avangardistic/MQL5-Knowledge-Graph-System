# MQL5 Knowledge Graph Report

Generated: 2026-08-27 15:50:59

## Project Statistics

- **Total Symbols**: 24
- **Total Edges**: 129
- **Total Files**: 2

### Symbols by Type

- event_handler: 3
- function: 13
- global_variable: 6
- property: 2

## Files Overview

### RiskManager.mqh

- Path: `sample_mql5/RiskManager.mqh`
- Lines: 123
- Size: 4023 bytes

**Symbols:**

*functions:*
- `CalculateLotSize` (line 16)
- `CanOpenPosition` (line 40)
- `IsDailyLimitReached` (line 54)
- `ResetDailyStats` (line 94)
- `GetCurrentRiskPercent` (line 103)
- `IsAccountInDanger` (line 118)

*global_variables:*
- `0` (line 23)
- `lots` (line 34)
- `false` (line 43)
- `true` (line 48)
- `currentTime` (line 56)

### SampleEA.mq5

- Path: `sample_mql5/SampleEA.mq5`
- Lines: 194
- Size: 6207 bytes

**Symbols:**

*event_handlers:*
- `OnInit` (line 19)
- `OnDeinit` (line 36)
- `OnTick` (line 45)

*functions:*
- `OpenBuyOrder` (line 76)
- `CloseAllPositions` (line 104)
- `ClosePosition` (line 119)
- `CountPositions` (line 146)
- `PositionsTotal` (line 148)
- `TrailPositions` (line 154)
- `ModifyPositionSL` (line 179)

*global_variables:*
- `handleMA` (line 13)

*propertys:*
- `property_copyright` (line 5)
- `property_version` (line 6)

## File Dependencies

## Event Handlers

### OnDeinit

- File: `sample_mql5/SampleEA.mq5`
- Line: 36

### OnInit

- File: `sample_mql5/SampleEA.mq5`
- Line: 19

### OnTick

- File: `sample_mql5/SampleEA.mq5`
- Line: 45

## Call Graph Summary

Total function calls mapped: 105

### Top Called Functions

- `PositionsTotal`: called 20 times
- `ModifyPositionSL`: called 17 times
- `TrailPositions`: called 11 times
- `ClosePosition`: called 10 times
- `GetCurrentRiskPercent`: called 9 times
- `CountPositions`: called 9 times
- `CloseAllPositions`: called 7 times
- `OpenBuyOrder`: called 6 times
- `IsAccountInDanger`: called 5 times
- `IsDailyLimitReached`: called 4 times
- `ResetDailyStats`: called 3 times
- `OnTick`: called 2 times
- `CanOpenPosition`: called 1 times
- `OnDeinit`: called 1 times
