"""Independent behavioral grades for local runner fixtures; no model evaluation."""
import importlib.util
import json
import sys
from pathlib import Path

workspace, task = Path(sys.argv[1]), sys.argv[2]
spec = importlib.util.spec_from_file_location('candidate_app', workspace / 'app.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
solve = module.solve
cases = 0


def check(actual, expected):
    global cases
    assert actual == expected, (actual, expected)
    cases += 1


def raises(exception, *args):
    global cases
    try:
        solve(*args)
    except exception:
        cases += 1
    else:
        raise AssertionError('Expected ' + exception.__name__)


if task == 'quoted-csv':
    for text, expected in [('', []), ('a,b\n', [['a','b']]), ('"a,b",c\n', [['a,b','c']]),
                           ('"a\nb",c\n', [['a\nb','c']]), ('"""quoted""",ü\r\n', [['"quoted"','ü']]),
                           ('a,,c\n', [['a','','c']]), ('a,b\nc,d', [['a','b'],['c','d']])]:
        check(solve(text), expected)
elif task == 'decimal-total':
    for values, expected in [([], '0.00'), (['0.1','0.2'], '0.30'), (['1.005'], '1.01'),
                             (['-1.005'], '-1.01'), (['1000000000.01','-0.01'], '1000000000.00'),
                             (['0.004','0.004'], '0.01')]:
        check(solve(values), expected)
    raises(ValueError, ['NaN'])
    raises(ValueError, ['Infinity'])
elif task == 'merge-intervals':
    for values, expected in [([], []), ([(2,3),(1,2)], [(1,3)]), ([(1,4),(2,3)], [(1,4)]),
                             ([(1,2),(4,5)], [(1,2),(4,5)]), ([(2,2),(2,2)], [(2,2)]),
                             ([(-5,-1),(-2,3)], [(-5,3)])]:
        check(solve(values), expected)
    raises(ValueError, [(3,1)])
elif task == 'stable-unique':
    for values, expected in [([], []), ([1,2,1,3,2], [1,2,3]), ([[1],[2],[1]], [[1],[2]]),
                             ([{'a':1},{'a':1},{'b':2}], [{'a':1},{'b':2}]),
                             (['Ü','ü','Ü'], ['Ü','ü']), ([None,None,False], [None,False])]:
        check(solve(iter(values)), expected)
elif task == 'safe-relative':
    for value, expected in [('a/b','a/b'), ('a//b','a/b'), ('./a','a'), ('','.'), ('ü/a','ü/a')]:
        check(solve(value), expected)
    for value in ('../a','a/../b','/etc/passwd','a/../../b'):
        raises(ValueError, value)
elif task == 'topological-order':
    check(solve([], []), [])
    check(solve(['c','a','b'], []), ['a','b','c'])
    check(solve(['c','a','b'], [('a','c'),('a','b')]), ['a','b','c'])
    check(solve(['a','b'], [('a','b'),('a','b')]), ['a','b'])
    raises(ValueError, ['a','b'], [('a','b'),('b','a')])
    raises(ValueError, ['a'], [('a','a')])
    raises(ValueError, ['a'], [('a','missing')])
elif task == 'retry-budget':
    check(solve(lambda: 7, 1), 7)
    check(solve(lambda: None, 3), None)
    for failures in (1,2,3):
        history = []
        def operation():
            history.append(1)
            if len(history) <= failures:
                raise ValueError('retryable')
            return len(history)
        check(solve(operation, failures + 1), failures + 1)
        check(len(history), failures + 1)
    raises(ValueError, lambda: 0, 0)
    def fatal():
        raise TypeError('must not retry')
    raises(TypeError, fatal, 3)
elif task == 'rolling-window':
    for values, width, expected in [([],2,[]), ([1],2,[]), ([1,2,3],2,[(1,2),(2,3)]),
                                    ([1,2],1,[(1,),(2,)]), ([1,2],2,[(1,2)]),
                                    (['a','ü','z'],2,[('a','ü'),('ü','z')])]:
        check(solve(iter(values), width), expected)
    raises(ValueError, [1,2], 0)
elif task == 'strict-json-lines':
    for value, expected in [('',[]), (' \n\t\n',[]), ('1\ntrue\nnull\n',[1,True,None]),
                             ('{"x":"ü"}\n[1,2]',[{'x':'ü'},[1,2]]), ('"line\\nbreak"\n',['line\nbreak'])]:
        check(solve(value), expected)
    for value in ('NaN\n', 'Infinity\n', '{bad}\n'):
        raises(ValueError, value)
elif task == 'utc-sort':
    for values, expected in [([],[]), (['2026-01-01T00:00:00Z'],['2026-01-01T00:00:00Z']),
                             (['2026-01-01T01:00:00+02:00','2025-12-31T23:30:00Z'],
                              ['2026-01-01T01:00:00+02:00','2025-12-31T23:30:00Z']),
                             (['2026-01-01T00:00:00','2025-12-31T23:59:59Z'],
                              ['2025-12-31T23:59:59Z','2026-01-01T00:00:00']),
                             (['2026-01-01T00:00:00Z','2026-01-01T01:00:00+01:00'],
                              ['2026-01-01T00:00:00Z','2026-01-01T01:00:00+01:00'])]:
        check(solve(values), expected)
    raises(ValueError, ['invalid'])
elif task == 'unicode-word-count':
    for text, expected in [('',{}), ('Hello HELLO',{'hello':2}), ('Straße STRASSE',{'strasse':2}),
                            ('a_b 123 c',{'a':1,'b':1,'c':1}), ('café CAFÉ',{'café':2}),
                            ('中文 中文',{'中文':2}), ('one-two',{'one':1,'two':1})]:
        check(solve(text), expected)
elif task == 'nested-redaction':
    value = {'Password':'p','nested':[{'token':'t','token_count':2}], 'SECRET':{'x':'hidden'}, 'ok':None}
    original = json.loads(json.dumps(value))
    check(solve(value), {'Password':'[REDACTED]','nested':[{'token':'[REDACTED]','token_count':2}],
                         'SECRET':'[REDACTED]','ok':None})
    check(value, original)
    check(solve({'x':1}), {'x':1})
    check(solve([{'secret':'x'},1,None]), [{'secret':'[REDACTED]'},1,None])
    check(solve('safe'), 'safe')
    check(solve({}), {})
else:
    raise ValueError('Unknown grading task: ' + task)
print(json.dumps({'task_id':task,'passed_cases':cases,'kind':'independent-local-grader'}))
