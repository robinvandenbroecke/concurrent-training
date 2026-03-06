# Enum Unification Refactor Plan

## ✅ COMPLETED - Sprint E1

**Status**: All enum centralization tasks completed.  
**Date**: 2024-03-06  
**Tests**: 10 new tests added, all 449 tests passing.

### Summary of Changes

- Removed duplicate `LiftType` from `app/domain/day_engine.py`
- Removed duplicate `EnduranceMode` from `app/domain/day_engine.py` (now uses `EnduranceSport` alias)
- Updated `app/services/engine_orchestrator.py` to use canonical enums
- Added `CLEAN` value to `LiftType` for backwards compatibility
- Added `OTHER` values to all enums
- Added comprehensive regression tests in `tests/test_enum_centralization.py`

### Canonical Source of Truth

All enums now live in **`app/types.py`**:

```python
from app.types import LiftType, EnduranceSport, EnduranceIntensity
```

These are re-exported from:
- `app/domain/__init__.py`
- `app/domain/day_engine.py` (EnduranceMode = EnduranceSport for backwards compat)

---

## Executive Summary (Original)

This document outlines a plan to eliminate duplicate enum definitions (`LiftType`, `EnduranceSport`, `EnduranceIntensity`) across the concurrent-training codebase. Currently, these enums are defined in three different locations, causing type mismatches and potential runtime errors.

---

## 1. Current State Analysis

### 1.1 Enum Definitions (❌ Duplicate Sources)

| Enum | File | Lines | Status |
|------|------|-------|--------|
| `LiftType` | `app/types.py` | 5-11 | ✅ Canonical source |
| `LiftType` | `app/domain/model.py` | 11-16 | ❌ Duplicate (also imports from types) |
| `LiftType` | `app/models.py` | 11-17 | ❌ Duplicate (also imports from types) |
| `LiftType` | `app/schemas.py` | 7-13 | ❌ Duplicate (no import) |
| `EnduranceSport` | `app/types.py` | 14-18 | ✅ Canonical source |
| `EnduranceSport` | `app/domain/model.py` | 18-21 | ❌ Duplicate (also imports from types) |
| `EnduranceSport` | `app/models.py` | 19-22 | ❌ Duplicate (also imports from types) |
| `EnduranceSport` | `app/schemas.py` | 15-19 | ❌ Duplicate (no import) |
| `EnduranceIntensity` | `app/types.py` | 21-25 | ✅ Canonical source |
| `EnduranceIntensity` | `app/domain/model.py` | 23-26 | ❌ Duplicate (also imports from types) |

### 1.2 Current Import Graph

```
app/types.py (canonical definitions)
    ↑
    ├── app/domain/model.py (imports but ALSO redefines!) Lines 8-9
    ├── app/models.py (imports but ALSO redefines!) Lines 9
    ↑
    ├── app/services.py imports from app.domain.model
    ├── app/main.py imports from app.domain.model
    ├── app/cli.py imports from app.models AND app.domain.model
    └── tests/test_domain.py imports from app.domain.model

app/schemas.py (standalone duplicates, NO imports from types!)
    ↑
    ├── app/services.py imports schemas
    ├── app/main.py imports schemas
    └── app/cli.py imports schemas
```

### 1.3 Current Enum Definitions (Side-by-Side Comparison)

**app/types.py (Canonical - KEEP):**
```python
class LiftType(str, Enum):
    """Weightlifting movement types"""
    SQUAT = "squat"
    BENCH = "bench"
    DEADLIFT = "deadlift"
    PRESS = "press"
    POWER_CLEAN = "power_clean"


class EnduranceSport(str, Enum):
    """Endurance sport types"""
    RUNNING = "running"
    CYCLING = "cycling"
    SWIMMING = "swimming"


class EnduranceIntensity(str, Enum):
    """Endurance training intensity zones"""
    Z2 = "z2"  # Zone 2, aerobic, builds R_mito
    HIIT = "hiit"  # High intensity, adds E_fat and interference
```

**app/domain/model.py (Duplicate - REMOVE):**
```python
class LiftType(str, Enum):
    SQUAT = "squat"
    BENCH = "bench"
    DEADLIFT = "deadlift"
    PRESS = "press"
    POWER_CLEAN = "power_clean"


class EnduranceSport(str, Enum):
    RUNNING = "running"
    CYCLING = "cycling"
    SWIMMING = "swimming"


class EnduranceIntensity(str, Enum):
    Z2 = "z2"  # Zone 2, aerobic, builds R_mito
    HIIT = "hiit"  # High intensity, adds E_fat and interference
```

**app/models.py (Duplicate - REMOVE):**
```python
class LiftType(str, enum.Enum):
    SQUAT = "squat"
    BENCH = "bench"
    DEADLIFT = "deadlift"
    PRESS = "press"
    POWER_CLEAN = "power_clean"


class EnduranceSport(str, enum.Enum):
    RUNNING = "running"
    CYCLING = "cycling"
    SWIMMING = "swimming"
```

**app/schemas.py (Duplicate - REMOVE):**
```python
class LiftType(str, Enum):
    SQUAT = "squat"
    BENCH = "bench"
    DEADLIFT = "deadlift"
    PRESS = "press"
    POWER_CLEAN = "power_clean"


class EnduranceSport(str, Enum):
    RUNNING = "running"
    CYCLING = "cycling"
    SWIMMING = "swimming"
```

### 1.4 Usage Analysis by File

| File | Current Import | Usage Count | Action Required |
|------|---------------|-------------|-----------------|
| `app/domain/model.py` | Self-defined | ~25 references | Remove definition, update imports |
| `app/models.py` | Self-defined | ~8 references | Remove definition, update imports |
| `app/schemas.py` | Self-defined | ~6 references | Remove definition, update imports |
| `app/services.py` | `app.domain.model` | ~15 references | Update import to `app.types` |
| `app/main.py` | `app.domain.model` | ~4 references | Update import to `app.types` |
| `app/cli.py` | `app.models`, `app.domain.model` | ~8 references | Update imports to `app.types` |
| `tests/test_domain.py` | `app.domain.model` | ~8 references | Update import to `app.types` |

---

## 2. Target State

### 2.1 Single Source of Truth Architecture

```
app/types.py (ONLY definition)
    ↑
    ├── app/domain/model.py (imports only)
    ├── app/models.py (imports only)
    ├── app/schemas.py (imports only)
    ├── app/services.py (imports from types)
    ├── app/main.py (imports from types)
    ├── app/cli.py (imports from types)
    └── tests/test_domain.py (imports from types)
```

### 2.2 Target `app/types.py` (Unchanged)

The existing `app/types.py` is already the correct canonical source - no changes needed:

```python
"""Shared type definitions - single source of truth for enums"""
from enum import Enum


class LiftType(str, Enum):
    """Weightlifting movement types"""
    SQUAT = "squat"
    BENCH = "bench"
    DEADLIFT = "deadlift"
    PRESS = "press"
    POWER_CLEAN = "power_clean"


class EnduranceSport(str, Enum):
    """Endurance sport types"""
    RUNNING = "running"
    CYCLING = "cycling"
    SWIMMING = "swimming"


class EnduranceIntensity(str, Enum):
    """Endurance training intensity zones"""
    Z2 = "z2"  # Zone 2, aerobic, builds R_mito
    HIIT = "hiit"  # High intensity, adds E_fat and interference
```

---

## 3. Step-by-Step Migration Plan

### Phase 1: Update Schema Layer (app/schemas.py)

**File:** `app/schemas.py`
**Lines affected:** 1-20

**Changes:**
1. Remove duplicate enum definitions (lines 7-20)
2. Add import from `app.types`

**Before:**
```python
"""Pydantic schemas for API"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from datetime import datetime
from enum import Enum


class LiftType(str, Enum):
    SQUAT = "squat"
    BENCH = "bench"
    DEADLIFT = "deadlift"
    PRESS = "press"
    POWER_CLEAN = "power_clean"


class EnduranceSport(str, Enum):
    RUNNING = "running"
    CYCLING = "cycling"
    SWIMMING = "swimming"
```

**After:**
```python
"""Pydantic schemas for API"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from datetime import datetime

from app.types import LiftType, EnduranceSport
```

**Command:**
```bash
cd /root/clawd/projects/concurrent-training
```

**Verification:**
```python
# In Python REPL
from app.schemas import LiftType, EnduranceSport
from app.types import LiftType as TypesLiftType
assert LiftType is TypesLiftType  # Should be same object
```

---

### Phase 2: Update Database Models (app/models.py)

**File:** `app/models.py`
**Lines affected:** 1-25

**Changes:**
1. Remove duplicate enum definitions (lines 11-22)
2. Keep the import from `app.types` (line 9)

**Before:**
```python
"""Database models"""
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, 
    JSON, Enum as SQLEnum, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum


class LiftType(str, enum.Enum):
    SQUAT = "squat"
    BENCH = "bench"
    DEADLIFT = "deadlift"
    PRESS = "press"
    POWER_CLEAN = "power_clean"


class EnduranceSport(str, enum.Enum):
    RUNNING = "running"
    CYCLING = "cycling"
    SWIMMING = "swimming"


from app.types import LiftType, EnduranceSport  # Line 25
```

**After:**
```python
"""Database models"""
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, 
    JSON, Enum as SQLEnum, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

from app.types import LiftType, EnduranceSport
```

**Note:** The `SQLEnum` wrapper usage remains unchanged since `LiftType` and `EnduranceSport` are still the same enum classes.

---

### Phase 3: Update Domain Model (app/domain/model.py)

**File:** `app/domain/model.py`
**Lines affected:** 1-30

**Changes:**
1. Remove duplicate enum definitions (lines 14-26)
2. Keep the import from `app.types`

**Before:**
```python
"""
Concurrent Training Domain Model

Implements the mathematical model for fatigue, fitness, and autoregulation
in concurrent strength and endurance training.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
import math

from app.types import LiftType, EnduranceSport, EnduranceIntensity


class LiftType(str, Enum):
    SQUAT = "squat"
    BENCH = "bench"
    DEADLIFT = "deadlift"
    PRESS = "press"
    POWER_CLEAN = "power_clean"


class EnduranceSport(str, Enum):
    RUNNING = "running"
    CYCLING = "cycling"
    SWIMMING = "swimming"


class EnduranceIntensity(str, Enum):
    Z2 = "z2"  # Zone 2, aerobic, builds R_mito
    HIIT = "hiit"  # High intensity, adds E_fat and interference
```

**After:**
```python
"""
Concurrent Training Domain Model

Implements the mathematical model for fatigue, fitness, and autoregulation
in concurrent strength and endurance training.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math

from app.types import LiftType, EnduranceSport, EnduranceIntensity
```

---

### Phase 4: Update Services Layer (app/services.py)

**File:** `app/services.py`
**Lines affected:** 1-15

**Changes:**
1. Update imports to use `app.types` instead of `app.domain.model` for enums

**Before:**
```python
"""
Services layer - connects domain model to persistence
"""
from datetime import datetime, date
from typing import Optional, Dict, List
from sqlalchemy.orm import Session

from app.domain.model import (
    ConcurrentTrainingModel, Autoregulator, LiftType, EnduranceSport,
    DayLevelState, RepLevelState, SystemParameters as DomainParams
)
from app import models as db_models
from app import schemas
```

**After:**
```python
"""
Services layer - connects domain model to persistence
"""
from datetime import datetime, date
from typing import Optional, Dict, List
from sqlalchemy.orm import Session

from app.domain.model import (
    ConcurrentTrainingModel, Autoregulator,
    DayLevelState, RepLevelState, SystemParameters as DomainParams
)
from app.types import LiftType, EnduranceSport
from app import models as db_models
from app import schemas
```

---

### Phase 5: Update Main API (app/main.py)

**File:** `app/main.py`
**Lines affected:** 1-25

**Changes:**
1. Update imports to use `app.types` instead of `app.domain.model` for enums

**Before:**
```python
"""
FastAPI application - main entry point
"""
from contextlib import asynccontextmanager
from datetime import date
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine, Base
from app import models, schemas
from app.services import (
    AthleteService, SessionService, DayUpdateService,
    ReadinessService, AutoregulationService
)
from app.domain.model import LiftType, EnduranceSport
```

**After:**
```python
"""
FastAPI application - main entry point
"""
from contextlib import asynccontextmanager
from datetime import date
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine, Base
from app import models, schemas
from app.services import (
    AthleteService, SessionService, DayUpdateService,
    ReadinessService, AutoregulationService
)
from app.types import LiftType, EnduranceSport
```

---

### Phase 6: Update CLI (app/cli.py)

**File:** `app/cli.py`
**Lines affected:** 1-25

**Changes:**
1. Update imports to use `app.types` instead of `app.models` and `app.domain.model` for enums

**Before:**
```python
"""CLI for demo and administration"""
import sys
from datetime import datetime, timedelta
from typing import Optional

import typer
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine, Base
from app.models import (
    Athlete, StrengthSession, EnduranceSession, LiftProfile,
    DayState, LiftDayState, LiftType, EnduranceSport
)
from app.domain.model import (
    ConcurrentTrainingModel, LiftProfile as DomainProfile,
    Autoregulator, RepLevelState
)
```

**After:**
```python
"""CLI for demo and administration"""
import sys
from datetime import datetime, timedelta
from typing import Optional

import typer
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine, Base
from app.models import (
    Athlete, StrengthSession, EnduranceSession, LiftProfile,
    DayState, LiftDayState
)
from app.types import LiftType, EnduranceSport
from app.domain.model import (
    ConcurrentTrainingModel, LiftProfile as DomainProfile,
    Autoregulator, RepLevelState
)
```

---

### Phase 7: Update Tests (tests/test_domain.py)

**File:** `tests/test_domain.py`
**Lines affected:** 1-10

**Changes:**
1. Update imports to use `app.types` for enums

**Before:**
```python
"""Test suite for concurrent training model"""
import pytest
from datetime import datetime, date
import math

from app.domain.model import (
    ConcurrentTrainingModel, Autoregulator, LiftProfile, LiftType,
    DayLevelState, RepLevelState, SystemParameters, EnduranceSport
)
```

**After:**
```python
"""Test suite for concurrent training model"""
import pytest
from datetime import datetime, date
import math

from app.domain.model import (
    ConcurrentTrainingModel, Autoregulator, LiftProfile,
    DayLevelState, RepLevelState, SystemParameters
)
from app.types import LiftType, EnduranceSport
```

---

## 4. Backward Compatibility Considerations

### 4.1 Database Compatibility

**Status:** ✅ **NO MIGRATION NEEDED**

The SQLAlchemy `SQLEnum` column type stores enum values as strings in the database. Since all duplicate enum definitions use identical string values, the database schema and data remain compatible.

Example:
```python
# All three definitions produce the same database value:
LiftType.SQUAT.value  # Always "squat" regardless of source
```

### 4.2 API Compatibility

**Status:** ✅ **FULLY COMPATIBLE**

Pydantic models in `app/schemas.py` will use the same enum classes from `app/types.py`. Since the values are identical:
- API requests with `"squat"` will still validate correctly
- API responses will still serialize as `"squat"`
- OpenAPI schema generation remains unchanged

### 4.3 Internal Code Compatibility

**Status:** ✅ **FULLY COMPATIBLE**

All enum comparisons and operations remain identical:
```python
# These all work the same way:
lift == LiftType.SQUAT
lift in [LiftType.SQUAT, LiftType.BENCH]
LiftType.SQUAT.value == "squat"
```

### 4.4 Potential Breaking Changes (None Expected)

| Scenario | Risk Level | Mitigation |
|----------|-----------|------------|
| Import paths changed | None | All imports resolve to same object |
| Enum values changed | None | Values identical across all definitions |
| Database schema changed | None | String storage unchanged |
| API contract changed | None | Pydantic serialization identical |

---

## 5. Testing Strategy

### 5.1 Pre-Migration Verification

Run these commands to establish baseline:

```bash
cd /root/clawd/projects/concurrent-training

# 1. Verify current tests pass
python -m pytest tests/ -v

# 2. Verify API starts successfully
python -c "from app.main import app; print('✓ API imports OK')"

# 3. Verify CLI works
python -m app.cli init

# 4. Check for enum identity issues
python -c "
from app.domain.model import LiftType as DomainLT
from app.models import LiftType as ModelsLT
from app.schemas import LiftType as SchemasLT
from app.types import LiftType as TypesLT

print('Domain == Models:', DomainLT is ModelsLT)
print('Domain == Schemas:', DomainLT is SchemasLT)
print('Domain == Types:', DomainLT is TypesLT)
# Currently all False - problem we're solving!
"
```

### 5.2 Post-Migration Verification

After each phase, run:

```bash
# 1. Static type checking
python -m mypy app/ --ignore-missing-imports

# 2. Import verification
python -c "
from app.types import LiftType, EnduranceSport, EnduranceIntensity
from app.domain.model import ConcurrentTrainingModel
from app.models import StrengthSession, EnduranceSession
from app.schemas import StrengthSessionCreate, EnduranceSessionCreate
from app.services import SessionService
from app.main import app
print('✓ All imports successful')
"

# 3. Enum identity verification (should all be True now)
python -c "
from app.types import LiftType as TypesLT
from app.domain.model import LiftType as DomainLT
from app.schemas import LiftType as SchemasLT

print('Types is only source:', TypesLT is DomainLT is SchemasLT)
assert TypesLT is DomainLT is SchemasLT, 'Enum unification failed!'
print('✓ Enums unified successfully')
"

# 4. Run full test suite
python -m pytest tests/ -v

# 5. API integration test
python -c "
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
response = client.get('/health')
assert response.status_code == 200
print('✓ API health check passed')
"
```

### 5.3 Edge Case Testing

Test these specific scenarios:

```python
# Test 1: Enum comparison across modules
from app.types import LiftType
from app.schemas import StrengthSessionCreate

# This should work without issues
assert StrengthSessionCreate.__fields__['lift'].type_ is LiftType

# Test 2: Database enum storage
from app.models import StrengthSession
from sqlalchemy import inspect

# Verify column type
inspector = inspect(StrengthSession)
lift_col = [c for c in inspector.columns if c.name == 'lift'][0]
print(f"Lift column type: {lift_col.type}")

# Test 3: API request/response with enums
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# Create athlete first
response = client.post("/athletes", json={"name": "Test"})
athlete_id = response.json()["id"]

# Test strength session creation
response = client.post("/sessions/strength", json={
    "athlete_id": athlete_id,
    "lift": "squat",
    "start_time": "2024-01-01T10:00:00",
    "sets": []
})
print(f"Session creation status: {response.status_code}")
```

---

## 6. Risk Assessment

### 6.1 Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Import circularity | Low | Medium | Import order verified in plan |
| SQLAlchemy enum binding | Low | High | SQLEnum uses class reference, stays intact |
| Pydantic validation changes | Low | Medium | Same enum class = same validation |
| Missing import updates | Medium | Medium | Comprehensive grep search for all usages |
| Test failures | Low | Low | Full test suite run after each phase |

### 6.2 Rollback Plan

If issues occur:

1. **Immediate rollback:**
   ```bash
   git checkout -- app/domain/model.py app/models.py app/schemas.py
   git checkout -- app/services.py app/main.py app/cli.py
   git checkout -- tests/test_domain.py
   ```

2. **Verification after rollback:**
   ```bash
   python -m pytest tests/ -v
   python -c "from app.main import app; print('✓ Rollback successful')"
   ```

### 6.3 Confidence Level

| Phase | Confidence | Notes |
|-------|-----------|-------|
| Phase 1 (schemas.py) | High | Simple import change |
| Phase 2 (models.py) | High | SQLAlchemy compatible |
| Phase 3 (domain/model.py) | High | Core domain logic unchanged |
| Phase 4-7 (consumers) | High | Import path changes only |
| **Overall** | **High** | Low complexity, high test coverage |

---

## 7. Implementation Checklist

### Pre-Implementation
- [ ] Run baseline tests (`python -m pytest tests/ -v`)
- [ ] Create feature branch: `git checkout -b refactor/unify-enums`
- [ ] Backup database if in production

### Implementation Phases
- [ ] **Phase 1:** Update `app/schemas.py`
  - [ ] Remove duplicate enum definitions
  - [ ] Add import from `app.types`
  - [ ] Run tests
- [ ] **Phase 2:** Update `app/models.py`
  - [ ] Remove duplicate enum definitions
  - [ ] Keep existing import
  - [ ] Run tests
- [ ] **Phase 3:** Update `app/domain/model.py`
  - [ ] Remove duplicate enum definitions
  - [ ] Keep existing import
  - [ ] Run tests
- [ ] **Phase 4:** Update `app/services.py`
  - [ ] Update imports to use `app.types`
  - [ ] Run tests
- [ ] **Phase 5:** Update `app/main.py`
  - [ ] Update imports to use `app.types`
  - [ ] Run tests
- [ ] **Phase 6:** Update `app/cli.py`
  - [ ] Update imports to use `app.types`
  - [ ] Run tests
- [ ] **Phase 7:** Update `tests/test_domain.py`
  - [ ] Update imports to use `app.types`
  - [ ] Run tests

### Post-Implementation
- [ ] Run full test suite
- [ ] Verify enum identity: `python -c "from app.types import LiftType; from app.schemas import LiftType as S; assert LiftType is S"`
- [ ] Start API and test health endpoint
- [ ] Run CLI demo command
- [ ] Code review
- [ ] Merge to main

---

## 8. Summary

This refactor plan addresses the critical issue of duplicate enum definitions that can cause:
- Type mismatches in comparisons (`LiftType.SQUAT from domain != LiftType.SQUAT from schemas`)
- Potential runtime errors
- Confusion for developers

**The solution is straightforward:**
1. Keep `app/types.py` as the single source of truth (already correctly defined)
2. Remove duplicate definitions from `app/domain/model.py`, `app/models.py`, and `app/schemas.py`
3. Update all imports across the codebase to use `app.types`

**Estimated effort:** 30-45 minutes  
**Risk level:** Low  
**Testing required:** Full test suite run  
**Backward compatibility:** 100% maintained

---

## Appendix A: Quick Reference Commands

```bash
# Navigate to project
cd /root/clawd/projects/concurrent-training

# Run all tests
python -m pytest tests/ -v

# Verify enum unification
python -c "
from app.types import LiftType as T
from app.domain.model import LiftType as D
from app.schemas import LiftType as S
from app.models import LiftType as M
print('All unified:', T is D is S is M)
"

# Start API for manual testing
python -m uvicorn app.main:app --reload

# Run CLI demo
python -m app.cli demo
```

## Appendix B: Files Modified Summary

| File | Lines Changed | Change Type |
|------|---------------|-------------|
| `app/schemas.py` | -14, +2 | Remove definitions, add import |
| `app/models.py` | -13, +1 | Remove duplicate definitions |
| `app/domain/model.py` | -14, +1 | Remove duplicate definitions |
| `app/services.py` | -2, +3 | Update import paths |
| `app/main.py` | -1, +1 | Update import path |
| `app/cli.py` | -2, +2 | Update import paths |
| `tests/test_domain.py` | -2, +3 | Update import paths |
| **Total** | **~35 lines** | **7 files** |
