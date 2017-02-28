# timedRun

> A shell command launcher with timeout and return status, extracted from lithium.

```python
import timedRun

r = timedRun.timed_run(['ls', '-l'], 5, 'logprefix')

if r.sta == timedRun.Status.NORMAL:
    print 'NORMAL'
```