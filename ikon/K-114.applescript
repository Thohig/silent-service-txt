-- Startar K-114 i eget fönster (fonster.py) med ubåtsikonen i Docken.
-- Bygg appen i code-mappen (appen ligger i ~/projekt):
--   osacompile -o ~/projekt/K-114.app ikon/K-114.applescript
--   cp ikon/K-114.icns ~/projekt/K-114.app/Contents/Resources/applet.icns
--   rm -f ~/projekt/K-114.app/Contents/Resources/Assets.car
--   codesign --force --sign - ~/projekt/K-114.app
-- Appen själv avslutas direkt; fönstret är spelets egen process. Fel hamnar i logs/fonster.log.

do shell script "cd '/Users/stefan/code/silent service-txt' && mkdir -p logs && /opt/homebrew/bin/uv run --extra fonster fonster.py > logs/fonster.log 2>&1 &"
