# log-exporters
A collection of scripts to export various data dumps into human-parsable logs

The scripts depend on a few different packages to correctly interpret the files and deal with unicode conversion.
To install these dependencies, run the following command:

    pip install --user -r requirements.txt

Additionally, signal_desktop.py requires the pysqlcipher module to read the stored messages, which is its own special
duck.  On Linux, all that's required to get it up and going is the following:

    pip install --user pysqlcipher --install-option="--bundled"

On Windows, what worked for me was to install the [MS VC++ Compiler for Python 2.7](https://www.microsoft.com/en-us/download/details.aspx?id=44266)
and [Win32 OpenSSL v1.0.2q](https://slproweb.com/products/Win32OpenSSL.html), then run the above `pip install` command.  Of particular
note is the version of OpenSSL (versions after 1.0.2 don't have libeay.dll included, which is needed for linking purposes) and the
32/64-bit nature of it, which must match the version of Python you have installed.  Once I had both of those working, the `pip install`
command worked and I had the library available to use on my system.

On Mac, this is easiest with [Homebrew](https://docs.brew.sh/Installation).  Once you have Homebrew up and going, install
the `sqlcipher` package with this command:

    brew install sqlcipher

Then, use pip to install `pysqlcipher`, but leave off the `--bundled` to make it link to the system copy of `libsqlcipher`:

    pip install --user pysqlcipher

