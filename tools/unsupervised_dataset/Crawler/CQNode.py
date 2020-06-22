class CQNode:
    """ This object holds information and metadata for links that the crawler will explore next. Each node
        contains the URL to be crawled and the depth of the crawler at the node in relation to the initial
        starting link.
    """
    
    def __init__(self, url, depth):
        """ Initializes a node to be used in the crawler queue.
        
        Args:
            url: The URL for the page being queued.
            depth: The depth of the node.
        """
        self.url = url
        self.depth = depth
        
    def getURL(self):
        """ Returns the URL for the page referenced by the node.
        
        Returns:
            A string containing a URL.
        """
        return self.url
    
    def getDepth(self):
        """ Returns the node depth.
        
        Returns:
            An integer representing node depth.
        """
        return self.depth
        