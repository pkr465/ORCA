// Missing SPDX header
// Missing copyright

#include <stdio.h>  // Wrong include order - system before own
#include <stdlib.h>
#include "sample_bad.h"

typedef struct {   // Unnecessary typedef
    int Value;     // CamelCase member
    char *pName;   // Hungarian notation
} MyStruct;

extern int global_var;  // extern in .c file

int CamelCaseFunction( int arg1,int arg2 )  // CamelCase, spaces inside parens, no space after comma
{
  int i;   // spaces instead of tabs
  int result = 0;
  
  if(arg1 > 0){   // no space after if, K&R violation
    for(i = 0; i < arg2; i++)   // no space after for
    {
      result += i;
    }
  }
  
  // This is a very very very very very very very very very very very very long line that exceeds 80 characters
  
  #define UNSAFE_MACRO(x) x * 2   // no parens around arg
  #define MULTI_LINE_MACRO(x) \
    if (x) \
      do_thing(x)   // no do-while wrapper
  
  return result;   
}

// Function that is way too long
int really_long_function(void)
{
  int a = 1;
  int b = 2;
  int c = 3;
  int d = 4;
  int e = 5;
  int f = 6;
  int g = 7;
  int h = 8;
  int i = 9;
  int j = 10;
  int k = 11;
  int l = 12;
  int m = 13;
  int n = 14;
  int o = 15;
  int p = 16;
  int q = 17;
  int r = 18;
  int s = 19;
  int t = 20;
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
