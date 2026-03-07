package org.kxml2.io

import android.util.Xml
import org.xmlpull.v1.XmlSerializer

/**
 * Compatibility shim for libraries that instantiate kxml2's serializer directly.
 * Delegates to Android's built-in Xml serializer implementation.
 */
class KXmlSerializer : XmlSerializer by Xml.newSerializer()
