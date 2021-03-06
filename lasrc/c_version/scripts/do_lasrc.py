#! /usr/bin/env python
import sys
import os
import re
import commands
import datetime
from optparse import OptionParser
import logging

ERROR = 1
SUCCESS = 0


#############################################################################
# Created on August 26, 2014 by Gail Schmidt, USGS/EROS
# Created Python script to run the Landsat 8 surface reflectance code based
# on the inputs specified by the user.  This script will determine the input
# auxiliary file needed for processing, based on the date of the Landsat 8
# input file.
#
# History:
#   Updated on 9/9/2014 by Gail Schmidt, USGS/EROS
#   Use standard python logging instead of a user-defined log file
#
#   Updated on 11/13/2015 by Gail Schmidt, USGS/EROS
#   Removed the --usebin command line argument.  All executables are expected
#       to be in the PATH.
#
#   Updated on 1/13/2016 by Gail Schmidt, USGS/EROS
#   Modified to support the new collection filenaming convention
#
#   Updated on 8/24/2016 by Gail Schmidt, USGS/EROS
#   Modified to flag collection scenes for special handling of QA output
#       in LaSRC processing. Additional command-line option is passed to
#       the lasrc executable.
#
# Usage: do_lasrc.py --help prints the help message
############################################################################
class SurfaceReflectance():

    def __init__(self):
        pass


    ########################################################################
    # Description: runSr will use the parameters passed for the input and
    # output files.  If input/output files are None (i.e. not specified) then
    # the command-line parameters will be parsed for this information.  The
    # surface reflectance application is then executed to generate the desired
    # outputs on the specified input file.  If a log file was specified, then
    # the output from this application will be logged to that file.
    #
    # Inputs:
    #   xml_infile - name of the input XML file
    #   process_sr - specifies whether the surface reflectance processing,
    #       should be completed.  True or False.  Default is True, otherwise
    #       the processing will halt after the TOA reflectance products are
    #       complete.
    #
    # Returns:
    #     ERROR - error running the surface reflectance application
    #     SUCCESS - successful processing
    #
    # Notes:
    #   1. The script obtains the path of the XML file and changes
    #      directory to that path for running the surface reflectance
    #      application.  If the XML file directory is not writable, then this
    #      script exits with an error.
    #   2. If the XML file is not specified and the information is
    #      going to be grabbed from the command line, then it's assumed all
    #      the parameters will be pulled from the command line.
    #######################################################################
    def runSr (self, xml_infile=None, process_sr=None, write_toa=False):
        # if no parameters were passed then get the info from the
        # command line
        if xml_infile == None:
            # Get version number
            cmdstr = ('lasrc --version')
            (status, self.version) = commands.getstatusoutput(cmdstr)

            # get the command line argument for the XML file
            parser = OptionParser(version = self.version)
            parser.add_option ("-i", "--xml", type="string",
                dest="xml",
                help="name of XML file", metavar="FILE")
            parser.add_option ("-s", "--process_sr", type="string",
                dest="process_sr",
                help="process the surface reflectance products; " + \
                     "True or False (default is True)  If False, then " + \
                     "processing will halt after the TOA reflectance " + \
                     "products are complete.")
            parser.add_option ("--write_toa", dest="write_toa", default=False,
                action="store_true",
                help="write the intermediate TOA reflectance products")
            (options, args) = parser.parse_args()
    
            # XML input file
            xml_infile = options.xml
            if xml_infile == None:
                parser.error ("missing input XML file command-line argument");
                return ERROR

            # surface reflectance options
            process_sr = options.process_sr
            write_toa = options.write_toa

        # get the logger
        logger = logging.getLogger(__name__)
        msg = 'Surface reflectance processing of Landsat file: %s' % xml_infile
        logger.info (msg)
        
        # make sure the XML file exists
        if not os.path.isfile(xml_infile):
            msg = "Error: XML file does not exist or is not accessible: " + \
                xml_infile
            logger.error (msg)
            return ERROR

        # use the base XML filename and not the full path.
        base_xmlfile = os.path.basename (xml_infile)
        msg = 'Processing XML file: %s' % base_xmlfile
        logger.info (msg)
        
        # get the path of the XML file and change directory to that location
        # for running this script.  save the current working directory for
        # return to upon error or when processing is complete.  Note: use
        # abspath to handle the case when the filepath is just the filename
        # and doesn't really include a file path (i.e. the current working
        # directory).
        mydir = os.getcwd()
        xmldir = os.path.dirname (os.path.abspath (xml_infile))
        if not os.access(xmldir, os.W_OK):
            msg = 'Path of XML file is not writable: %s.  Script needs ' + \
                'write access to the XML directory.' % xmldir
            logger.error (msg)
            return ERROR
        msg = 'Changing directories for surface reflectance processing: %s' % \
            xmldir
        logger.info (msg)
        os.chdir (xmldir)

        # pull the date from the XML filename to determine which auxiliary
        # file should be used for input.  Example: LC80410272013181LGN00.xml
        # uses L8ANC2013181.hdf_fused.  Similarly, the new collection naming
        # convention LC08_L1TP_041027_20130630_20140312_02.xml also used the
        # 2013181 HDF file.
        l8_prefixes_old = ['LC8', 'LO8']
        l8_prefixes_collection = ['LC08', 'LO08']
        if base_xmlfile[0:3] in l8_prefixes_old:
            # Old-style Level-1 naming convention. Just pull the year and DOY
            # from the XML filename.
            processing_collection = False
            aux_file = 'L8ANC' + base_xmlfile[9:16] + '.hdf_fused'
        elif base_xmlfile[0:4] in l8_prefixes_collection:
            # New-style collection naming convention. Pull the year, month,
            # day from the XML filename. It should be the 4th group, separated
            # by underscores. Then convert month, day to DOY.
            processing_collection = True
            aux_date = base_xmlfile.split('_')[3]
            aux_year = aux_date[0:4]
            aux_month = aux_date[4:6]
            aux_day = aux_date[6:8]
            myday = datetime.date(int(aux_year), int(aux_month), int(aux_day))
            aux_doy = myday.strftime("%j")
            aux_file = 'L8ANC' + aux_year + aux_doy + '.hdf_fused'
        else:
            msg = ('Base XML filename is not recognized as a valid Landsat8 '
                   'scene name' + base_xmlfile)
            logger.error (msg)
            os.chdir (mydir)
            return ERROR

        # if processing collections, the per-pixel angle bands need to be
        # generated for band 4 (representative band)
        if processing_collection:
            cmdstr = "create_l8_angle_bands --xml %s" % (base_xmlfile)
#            logger.debug('per-pixel angles command: {0}'.format(cmdstr))
            (status, output) = commands.getstatusoutput(cmdstr)
            logger.info(output)
            exit_code = status >> 8
            if exit_code != 0:
                logger.error('Error running create_l8_angle_bands. Processing '
                             'will terminate.')
                os.chdir(mydir)
                return ERROR

            # Mask the angle bands to match the band quality band
            cmdstr = ('mask_per_pixel_angles.py --xml {}'
                      .format(base_xmlfile))
            (status, output) = commands.getstatusoutput(cmdstr)
            logger.info(output)
            exit_code = status >> 8
            if exit_code != 0:
                logger.error('Error masking angle bands with the band '
                             'quality band. Processing will terminate.')
                return ERROR

        # determine the application name depending on whether or not we are
        # processing collection or pre-collection data
        if processing_collection:
            app_name = 'lasrc'
        else:
            app_name = 'lasrc_pre_collection'
 
        # run surface reflectance algorithm, checking the return status.  exit
        # if any errors occur.
        process_sr_opt_str = "--process_sr=true "
        write_toa_opt_str = ""

        if process_sr == "False":
            process_sr_opt_str = "--process_sr=false "
        if write_toa:
            write_toa_opt_str = "--write_toa "

        cmdstr = "%s --xml=%s --aux=%s %s%s--verbose" % \
            (app_name, xml_infile, aux_file, process_sr_opt_str,
             write_toa_opt_str)
        msg = 'Executing lasrc command: %s' % cmdstr
        logger.info (msg)
        (status, output) = commands.getstatusoutput (cmdstr)
        logger.info (output)
        exit_code = status >> 8
        if exit_code != 0:
            msg = 'Error running lasrc.  Processing will terminate.'
            logger.error (msg)
            os.chdir (mydir)
            return ERROR
        
        # successful completion.  return to the original directory.
        os.chdir (mydir)
        msg = 'Completion of surface reflectance.'
        logger.info (msg)
        return SUCCESS

######end of SurfaceReflectance class######

if __name__ == "__main__":
    # setup the default logger format and level. log to STDOUT.
    logging.basicConfig(format=('%(asctime)s.%(msecs)03d %(process)d'
                                ' %(levelname)-8s'
                                ' %(filename)s:%(lineno)d:'
                                '%(funcName)s -- %(message)s'),
                        datefmt='%Y-%m-%d %H:%M:%S',
                        level=logging.INFO)
    sys.exit (SurfaceReflectance().runSr())
