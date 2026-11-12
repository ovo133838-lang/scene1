"""Final quality commands using independently inspected original runner."""
import pathlib
source=pathlib.Path(__file__).with_name('independent_quality.py').read_text(encoding='utf-8')
source=source.replace('evidence/independent-testing','evidence/independent-testing-final').replace("'-count=1'","'-count=2'")
exec(compile(source,__file__,'exec'))
