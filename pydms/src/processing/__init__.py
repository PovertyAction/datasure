<<<<<<< HEAD
#-- DEFINE CONSTANTS FOR DATA PREP --#

# Data prep actions
DP_ACTIONS: tuple = ('transform column(s)', 
							'add column', 
							'delete column(s)', 
							'delete row(s)')

# Methods for deleting rows
DP_DEL_METHODS: tuple = ('by row index', 
					   'by condition')

DP_FUNCS: tuple = ('string', 
						  'numeric', 
						  'date')

DP_STR_FUNCS: tuple = ('substr', 'subinstr', 'strip', 
						 'lower', 'upper', 
						 'sting to number',
						 'string to date', 'str to datetime', 'extract pattern', 
						 'get dummies')

DP_NUM_FUNCS: tuple = ('add', 'multiple', 'subtract', 'divide', 
					  'number to string', 
					  'string to date', 'string to datetime', 
					  'extract pattern')

DP_DATETIME_FUNCS: tuple = ('day', 'week', 'month', 'year', 
<<<<<<< HEAD
							'second', 'minute', 'hour')
=======
							'second', 'minute', 'hour')
>>>>>>> fa2837e (restructured)
=======
from .prep import prep_load_log
>>>>>>> 9b1a5b9 (prep)
