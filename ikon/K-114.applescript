-- Startar K-114 i Terminal. Bygg appen i code-mappen:
--   osacompile -o ../K-114.app ikon/K-114.applescript
--   cp ikon/K-114.icns ../K-114.app/Contents/Resources/applet.icns
--   rm -f ../K-114.app/Contents/Resources/Assets.car
--   codesign --force --sign - ../K-114.app

set cmd to "cd '/Users/stefan/code/silent service-txt' && clear && /opt/homebrew/bin/uv run main.py; exit"
if application "Terminal" is running then
	tell application "Terminal"
		do script cmd
		activate
	end tell
else
	tell application "Terminal"
		activate
		repeat 50 times
			if (count of windows) > 0 then exit repeat
			delay 0.1
		end repeat
		do script cmd in window 1
	end tell
end if
delay 0.3
tell application "Terminal"
	try
		set number of columns of front window to 140
		set number of rows of front window to 42
	end try
end tell
