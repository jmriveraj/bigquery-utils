package com.google.bigquery;

import static java.lang.System.exit;

import org.apache.commons.cli.*;

import java.io.IOException;
import java.util.Comparator;

/**
 * This file is the main file for the command line tool.
 * Usage: query_breakdown -r <PATH> [-w <PATH>] [-l <INTEGER>]
 * -i, --inputFile, PATH: this command specifies the path to the file containing queries to be
 *                    inputted into the tool. It is therefore mandatory
 * -o, --outputFile, PATH: this command specifies the path to the file that the tool can write
 *                    its results to. If not specified, the tool will simply print results on the
 *                    console. It is therefore optional
 * -l, --limit, PATH: this command specifies the path to an integer that the tool takes as a
 *                    limit for the number of errors to be explored, thereby controlling the
 *                    runtime. It is therefore optional
 *
 * Sample Usage: query_breakdown -r input.txt
 *               query_breakdown -r input2.txt -w output.txt -l 3
 *               query_breakdown -r input3.txt -w output2.txt
 *               query_breakdown -r input4.txt -l 6
 */
public class Main {
  public static void main(String[] args) {
    String inputFile = null;
    int errorLimit = 0;
    String outputFile = null;
    CommandLine cl = createCommand(args);

    // if there is an error in parsing the commandline
    if (cl == null) {
      exit(1);
    }

    if (cl.hasOption("i")) {
      inputFile = cl.getOptionValue("i");
    }
    if (cl.hasOption("o")) {
      outputFile = cl.getOptionValue("o");
    }
    if (cl.hasOption("l")) {
      errorLimit = Integer.parseInt( cl.getOptionValue("l"));
    }

    // this is where we will put the file I/O logic through the input reader.
    String originalQuery = null;
    InputReader ir = new InputReader();
    try {
      originalQuery = ir.readInput(inputFile);
    } catch (IOException e) {
      System.out.println("there was an I/O error while reading the input");
      exit(1);
    }

    /* this is where we feed in the original query to QueryBreakdown, which will find
       all the unparseable components of the query and output them into the output file if
       specified. Otherwise, it will be autogenerated.
     */
    QueryBreakdown qb = new QueryBreakdown(new CalciteParser());
    qb.run(originalQuery, outputFile, errorLimit, ir.getLocationTracker());
  }

  /**
   * This is the method that instantiates a CommandLine object for the Apache CLI Interface.
   * It deals with command line parsing as well as help generation once parsing is unavailable
   */
  public static CommandLine createCommand(String[] args) {
    CommandLineParser parser = new DefaultParser();
    Options options = createOptions();
    HelpFormatter help = new HelpFormatter();

    help.setOptionComparator(new Comparator<Option>() {
      public int compare(Option option1, Option option2) {
        if (option1.isRequired() != option2.isRequired()) {
          return option1.isRequired() ? -1 : 1;
        }
        else if (option1.equals(option2)) {
          return 0;
        }
        else {
          return (option1.getLongOpt().equals("outputFile")) ? -1 : 1;
        }
      }
    });

    CommandLine cl = null;
    try {
      cl = parser.parse(options, args);
    } catch (ParseException e) {
      System.out.println("there was an issue parsing the commandline" + e.getMessage());
      help.printHelp("query_breakdown", options, true);
    }

    return cl;
  }

  /**
   * This is the method that instantiates options for the Apache CLI interface
   */
  public static Options createOptions() {
    Options options = new Options();
    options.addOption(Option.builder("i").required(true).longOpt("inputFile").hasArg(true)
        .argName("PATH").desc("this command specifies the path to the file "
            + "containing queries to be inputted into the tool. It is therefore mandatory")
        .build());
    options.addOption(Option.builder("o").longOpt("outputFile").hasArg(true).argName("PATH")
        .desc("this command specifies the path to the file that the tool can write "
            + "its results to. If not specified, the tool will simply print results"
            + "on the console. It is therefore optional").build());
    options.addOption(Option.builder("l").longOpt("limit").hasArg(true).argName("INTEGER")
        .desc("this command specifies the path to an integer that the tools takes "
            + "as a limit for the number of errors to be explored, thereby controlling"
            + "the runtime. It is therefore optional").build());
    return options;
  }
}