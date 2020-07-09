import java.io.BufferedReader;
import java.io.FileNotFoundException;
import java.io.FileReader;
import java.io.IOException;
import java.io.Reader;

/**
 * This class will take care of the input handling logic, essentially parsing the input document
 * into queries and data-cleaning if needed.
 */
public class InputReader {

  /**
   * This method will take in a txt file name, use BufferedReader to parse the input, and return
   * all the queries in a string format
   */
  public static String readInput(String filename) throws IOException {
    BufferedReader reader = null;
    String currentLine = "";
    try {
      reader = new BufferedReader(new FileReader((filename)));
    } catch (FileNotFoundException e) {
      System.out.println("A file of this name is not found");
    }

    StringBuilder sb = new StringBuilder();

    while (currentLine != null) {
      sb.append(currentLine);
      currentLine = reader.readLine();
    }

    reader.close();

    return sb.toString();
  }
}
