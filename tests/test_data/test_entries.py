test_items = {
'a':	True,
'b':	False,
'c':	'True',
'd':	'False',
'e':	1,
'f':	-1,
'g':	999999999,
'h':	0,
'i':	None,
'j':	'string',
'k':	"other_string",
'l':	';DROP TABLE OSMCSETTINGS;',
'm':	0.00,
'p':	-999.1,
'q':	1000000,
'r':	'98361',
'u':	'asjdgas"asdas"',
'v':	'',
}


test_items_replacements = {
'a':	'True',
'b':	'False',
'c':	True,
'd':	False,
'e':	1.0,
'f':	-1.0,
'g':	9999.99999,
'h':	'0',
'i':	88,
'j':	False,
'k':	True,
'l':	1,
'm':	'0.00',
'p':	False,
'q':	1000000.,
'r':	'aaa',
'u':	'asjdgas"asdas"',
'v':	None,
}
