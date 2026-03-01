// Missing SPDX license header - this is a violation
// Also missing proper copyright notice and module description

#include <stdio.h>
#include <stdlib.h>     // Bad include order
#include "bad_style.h"  // Own headers should come first

typedef struct {        // Typedef discouraged in kernel code
    int Value;          // CamelCase member name (should be snake_case)
    char *pName;        // Hungarian notation (not allowed)
    long long internal_field_with_very_long_name_that_makes_code_hard_to_read;
} MyStruct;

extern int global_var;  // extern in .c file is bad practice

/* Global variable without proper prefix */
int g_state = 0;

#define UNSAFE_MACRO(x) x * 2           // Missing parentheses around arg
#define MULTI_LINE_MACRO(x) \
	if (x) \                            // No do-while wrapper
		do_thing(x)

// This is a very long line that exceeds the standard 80 character limit and should be split into multiple lines to comply with style guides
static int CamelCaseFunction( int arg1,int arg2,int arg3 )  // CamelCase name, missing space after comma
{
  int i;                // Spaces instead of tabs for indentation - VIOLATION
  int result = 0;
  int counter=0;        // No space around operators

  if(arg1 > 0){         // Missing space after 'if'
    for(i = 0; i < arg2; i++)  // Missing space after 'for'
    {
      result += i;
      counter++ ;       // Extra space before ++
    }
  }

  // Nested function that is overly complex
  if (arg3 == 1)
  {
    int x=5,y=10,z=15;  // Multiple declarations, no spaces
    x = y+z;
    if (x>0)
    {
      result += x;
    }
  }

  return result;
}

// Function with inconsistent brace style
int really_long_function(void)
{
  int a=1,b=2,c=3,d=4,e=5,f=6,g=7;
  int h=8,i=9,j=10,k=11,l=12,m=13;
  int n=14,o=15,p=16,q=17,r=18,s=19,t=20;

  a = b + c + d + e;
  f = g + h + i + j;
  k = l + m + n + o;
  p = q + r + s + t;
  a = b + c + d + e;
  f = g + h + i + j;
  k = l + m + n + o;
  p = q + r + s + t;
  a = b + c + d + e;
  f = g + h + i + j;
  k = l + m + n + o;
  p = q + r + s + t;
  a = b + c + d + e;
  f = g + h + i + j;
  k = l + m + n + o;
  p = q + r + s + t;

  return a + f + k + p;
}

// Mixed indentation
void broken_function(void)
{
	int x = 0;          // Tab indent
  int y = 1;          // Space indent - MIXED
	int z = 2;          // Tab indent again

	if (x == 0) {       // K&R style - correct
    y = 2;            // But then switches to different style
	}
}

// Trailing whitespace on the line below
int with_trailing_space(void)
{
	return 0;
}
