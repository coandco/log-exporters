# log-exporters
A collection of scripts to export various data dumps into human-parsable logs

The scripts depend on a few different packages to correctly interpret the files and deal with unicode conversion.
To install these dependencies, run the following command:

    pip install --user -r requirements.txt
    
Additionally, signal_desktop.py requires that the sqlcipher executable be on your path somewhere.  On Linux and OSX, 
this is most easily done via their respective package managers (via `apt-get install sqlcipher`,
`brew install sqlcipher`, and the like).  On Windows, the sqlcipher.exe executable is most easily built on a system 
with Docker via https://github.com/coandco/docker_build_windows_sqlcipher.
